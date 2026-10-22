"""Upload controls and temporary-workspace analysis integration."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import streamlit as st

from vision_doctor.archive import ArchiveError
from vision_doctor.config import Settings
from vision_doctor.models import AuditReport, KnowledgeProfile
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
    quality_mode: Literal["fixed", "adaptive"] | None = None,
    knowledge_profile: KnowledgeProfile | str | None = None,
) -> Settings:
    """Return one validated settings snapshot from the visible controls."""

    image_quality = base.image_quality.model_copy(
        update={
            "mode": quality_mode or base.image_quality.mode,
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
    knowledge = base.knowledge.model_copy(
        update={
            "profile": (
                KnowledgeProfile(knowledge_profile)
                if knowledge_profile is not None
                else base.knowledge.profile
            )
        }
    )
    return base.model_copy(
        update={
            "image_quality": image_quality,
            "duplicate_detection": duplicate_detection,
            "knowledge": knowledge,
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
        raise ValueError("请上传 .zip 格式的数据集压缩包。")
    maximum = settings.upload.max_archive_size_mb * _MEBIBYTE
    if len(payload) > maximum:
        raise ValueError(
            f"上传文件超过 {settings.upload.max_archive_size_mb} MiB 限制。"
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
        return f"数据集结构或压缩包校验失败：{error}"
    if isinstance(error, ValueError):
        message = str(error)
        if message.startswith(("请上传", "上传文件超过")):
            return message
    return "体检未能完成。请检查 ZIP 目录结构和文件内容后重试。"


def render_upload(settings: Settings) -> None:
    """Render upload guidance, threshold controls, and the analyze action."""

    st.subheader("上传 YOLO Detection 数据集")
    st.markdown(
        "必需结构：`data.yaml`、`train/images` 和 `train/labels`。"
        "`val/images` + `val/labels`、`test/images` + `test/labels` 可选。"
        "ZIP 可以多一层数据集目录，根目录也允许包含 README、许可证等普通文件。"
    )
    st.info(
        "上传内容只在本次会话的随机临时目录中处理；VisionDoctor 不会修改源 ZIP。"
    )
    st.caption(
        f"限制：ZIP 最大 {settings.upload.max_archive_size_mb} MiB，"
        f"最多 {settings.upload.max_entries:,} 个文件，"
        f"解压后最大 {settings.upload.max_extracted_size_mb} MiB。"
    )
    profile_labels = {
        KnowledgeProfile.GENERIC.value: "通用目标检测",
        KnowledgeProfile.INDUSTRIAL_INSPECTION.value: "工业质检",
        KnowledgeProfile.RETAIL_DETECTION.value: "零售商品检测",
        KnowledgeProfile.SMALL_OBJECT_DETECTION.value: "小目标检测",
    }
    profile_values = [profile.value for profile in KnowledgeProfile]
    scenario_profile = st.selectbox(
        "应用场景",
        options=profile_values,
        index=profile_values.index(settings.knowledge.profile.value),
        format_func=profile_labels.__getitem__,
        help=(
            "选择本地、版本化的审核建议。指导内容仅供参考，不会替代体检报告中的检测事实。"
        ),
    )
    uploaded = st.file_uploader("选择数据集 ZIP", type=["zip"])
    maximum_upload_bytes = settings.upload.max_archive_size_mb * _MEBIBYTE
    upload_too_large = (
        uploaded is not None and uploaded.size > maximum_upload_bytes
    )
    if upload_too_large:
        st.error(
            f"上传文件超过 {settings.upload.max_archive_size_mb} MiB 限制。"
        )
    token = None
    if uploaded is not None:
        token = f"{uploaded.name}:{uploaded.size}:{getattr(uploaded, 'file_id', '')}"
    observe_upload(st.session_state, token)

    with st.expander("体检阈值", expanded=False):
        quality_mode = st.selectbox(
            "图片质量阈值模式",
            options=("fixed", "adaptive"),
            index=0 if settings.image_quality.mode == "fixed" else 1,
            format_func={"fixed": "固定阈值", "adaptive": "自适应阈值"}.__getitem__,
            help=(
                "自适应模式按 split 使用稳健统计进行校准；样本不足时自动回退固定阈值。"
            ),
        )
        min_dimension = st.number_input(
            "最小宽度或高度（像素）",
            min_value=32,
            max_value=4096,
            value=settings.image_quality.min_width,
            step=16,
        )
        blur_threshold = st.number_input(
            "模糊阈值（Laplacian 方差）",
            min_value=0.0,
            max_value=1000.0,
            value=float(settings.image_quality.blur_variance_threshold),
            step=5.0,
        )
        dark_threshold = st.number_input(
            "过暗阈值（灰度均值）",
            min_value=0.0,
            max_value=254.0,
            value=float(settings.image_quality.dark_mean_threshold),
            step=1.0,
        )
        bright_threshold = st.number_input(
            "过亮阈值（灰度均值）",
            min_value=1.0,
            max_value=255.0,
            value=float(settings.image_quality.bright_mean_threshold),
            step=1.0,
        )
        near_distance = st.number_input(
            "近似重复 pHash 距离",
            min_value=0,
            max_value=64,
            value=settings.duplicate_detection.near_duplicate_hamming_threshold,
            step=1,
        )
    allow_llm = st.checkbox(
        "使用已配置的外部 LLM 生成 Dataset Doctor 诊断",
        value=False,
        help=(
            "默认关闭。关闭时使用完整的确定性诊断；开启时只向外部服务发送聚合证据。"
        ),
    )
    if allow_llm:
        st.warning(
            "外部 API 请求可能产生费用；调用失败时仍会自动使用确定性诊断。"
        )

    if st.button(
        "开始数据集体检",
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
            quality_mode=quality_mode,
            knowledge_profile=scenario_profile,
        )
        try:
            with st.spinner("正在安全解压并执行数据质量检查……"):
                report, workspace = analyze_uploaded_bytes(
                    uploaded.getvalue(),
                    uploaded.name,
                    settings=active,
                )
            store_analysis(st.session_state, report, workspace)
            st.success("数据集体检完成，请在其他标签页查看结果。")
        except Exception as error:  # noqa: BLE001 - UI trust boundary
            st.error(safe_error_message(error))
