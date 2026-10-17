"""Upload controls and temporary-workspace analysis integration."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

import streamlit as st

from vision_doctor.archive import ArchiveError
from vision_doctor.config import Settings
from vision_doctor.models import AuditReport
from vision_doctor.parser import DatasetParseError
from vision_doctor.pipeline import run_pipeline
from vision_doctor.ui.state import observe_upload, store_analysis

_MEBIBYTE = 1024 * 1024


@dataclass
class UploadWorkspace:
    """A session-owned temporary upload that can be explicitly removed."""

    _temporary_directory: tempfile.TemporaryDirectory[str]
    archive_path: Path

    @property
    def root(self) -> Path:
        return Path(self._temporary_directory.name)

    def cleanup(self) -> None:
        self._temporary_directory.cleanup()


def build_ui_settings(
    base: Settings,
    *,
    min_dimension: int,
    blur_threshold: float,
    dark_threshold: float,
    bright_threshold: float,
    near_duplicate_distance: int,
    allow_llm: bool,
) -> Settings:
    """Return one validated settings snapshot from the visible controls."""

    image_quality = base.image_quality.model_copy(
        update={
            "min_width": min_dimension,
            "min_height": min_dimension,
            "blur_variance_threshold": blur_threshold,
            "dark_mean_threshold": dark_threshold,
            "bright_mean_threshold": bright_threshold,
        }
    )
    duplicate_detection = base.duplicate_detection.model_copy(
        update={"near_duplicate_hamming_threshold": near_duplicate_distance}
    )
    llm = base.llm.model_copy(update={"enabled": allow_llm and base.llm.enabled})
    return base.model_copy(
        update={
            "image_quality": image_quality,
            "duplicate_detection": duplicate_detection,
            "llm": llm,
        }
    )


def analyze_uploaded_bytes(
    payload: bytes,
    filename: str,
    *,
    settings: Settings,
) -> tuple[AuditReport, UploadWorkspace]:
    """Analyze an uploaded ZIP inside a random, session-owned temp directory."""

    if Path(filename).suffix.lower() != ".zip":
        raise ValueError("Please upload a .zip archive.")
    maximum = settings.upload.max_archive_size_mb * _MEBIBYTE
    if len(payload) > maximum:
        raise ValueError(
            f"Upload exceeds the configured {settings.upload.max_archive_size_mb} MiB limit."
        )
    temporary = tempfile.TemporaryDirectory(prefix="vision-doctor-ui-")
    workspace = UploadWorkspace(
        _temporary_directory=temporary,
        archive_path=Path(temporary.name) / "dataset.zip",
    )
    try:
        workspace.archive_path.write_bytes(payload)
        report = run_pipeline(
            workspace.archive_path,
            settings=settings,
            temp_root=workspace.root,
            run_doctor=True,
        )
    except Exception:
        workspace.cleanup()
        raise
    return report, workspace


def safe_error_message(error: Exception) -> str:
    """Map expected data errors to readable text without leaking internals."""

    if isinstance(error, (ArchiveError, DatasetParseError)):
        return str(error)
    if isinstance(error, ValueError):
        message = str(error)
        if message.startswith(("Please upload", "Upload exceeds")):
            return message
    return "Analysis could not be completed. Verify the ZIP structure and try again."


def render_upload(settings: Settings) -> None:
    """Render upload guidance, threshold controls, and the analyze action."""

    st.subheader("Upload a YOLO Detection dataset")
    st.markdown(
        "Expected: `data.yaml`, `images/`, and `labels/` (optionally with "
        "`train/` and `val/` splits). Only ZIP archives are accepted."
    )
    st.info(
        "Uploads are processed only in a random temporary directory for this session. "
        "VisionDoctor never edits the source archive."
    )
    st.caption(
        f"Limits: {settings.upload.max_archive_size_mb} MiB archive, "
        f"{settings.upload.max_entries:,} files, "
        f"{settings.upload.max_extracted_size_mb} MiB extracted."
    )
    uploaded = st.file_uploader("Dataset ZIP", type=["zip"])
    maximum_upload_bytes = settings.upload.max_archive_size_mb * _MEBIBYTE
    upload_too_large = (
        uploaded is not None and uploaded.size > maximum_upload_bytes
    )
    if upload_too_large:
        st.error(
            f"Upload exceeds the configured {settings.upload.max_archive_size_mb} MiB limit."
        )
    token = None
    if uploaded is not None:
        token = f"{uploaded.name}:{uploaded.size}:{getattr(uploaded, 'file_id', '')}"
    observe_upload(st.session_state, token)

    with st.expander("Audit thresholds", expanded=False):
        min_dimension = st.number_input(
            "Minimum width or height (px)",
            min_value=32,
            max_value=4096,
            value=settings.image_quality.min_width,
            step=16,
        )
        blur_threshold = st.number_input(
            "Blur threshold (Laplacian variance)",
            min_value=0.0,
            max_value=1000.0,
            value=float(settings.image_quality.blur_variance_threshold),
            step=5.0,
        )
        dark_threshold = st.number_input(
            "Dark threshold (grayscale mean)",
            min_value=0.0,
            max_value=254.0,
            value=float(settings.image_quality.dark_mean_threshold),
            step=1.0,
        )
        bright_threshold = st.number_input(
            "Bright threshold (grayscale mean)",
            min_value=1.0,
            max_value=255.0,
            value=float(settings.image_quality.bright_mean_threshold),
            step=1.0,
        )
        near_distance = st.number_input(
            "Near-duplicate pHash distance",
            min_value=0,
            max_value=64,
            value=settings.duplicate_detection.near_duplicate_hamming_threshold,
            step=1,
        )
    allow_llm = st.checkbox(
        "Use configured external LLM for Dataset Doctor",
        value=False,
        help=(
            "Off by default. When off, the complete deterministic fallback is used. "
            "When on, only aggregate evidence is sent using configured credentials."
        ),
    )
    if allow_llm:
        st.warning(
            "An external API request may incur cost. Provider failures still use the "
            "deterministic fallback."
        )

    if st.button(
        "Start dataset health check",
        type="primary",
        disabled=uploaded is None or upload_too_large,
    ):
        active = build_ui_settings(
            settings,
            min_dimension=int(min_dimension),
            blur_threshold=float(blur_threshold),
            dark_threshold=float(dark_threshold),
            bright_threshold=float(bright_threshold),
            near_duplicate_distance=int(near_distance),
            allow_llm=allow_llm,
        )
        try:
            with st.spinner("Running safe extraction and deterministic checks…"):
                report, workspace = analyze_uploaded_bytes(
                    uploaded.getvalue(),
                    uploaded.name,
                    settings=active,
                )
            store_analysis(st.session_state, report, workspace)
            st.success("Dataset health check complete. Review the other tabs.")
        except Exception as error:  # noqa: BLE001 - UI trust boundary
            st.error(safe_error_message(error))
