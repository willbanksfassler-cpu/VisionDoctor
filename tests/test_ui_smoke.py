"""Objective smoke coverage for the Streamlit shell and UI integration helpers."""

from __future__ import annotations

import json
from pathlib import Path

import app
from scripts.generate_demo_dataset import generate_demo_zip
from vision_doctor.config import Settings
from vision_doctor.models import AuditReport
from vision_doctor.parser import DatasetParseError
from vision_doctor.ui.dashboard import TAB_LABELS
from vision_doctor.ui.issue_explorer import (
    class_ids_for_issue,
    filter_issues,
    image_for_issue,
    split_for_path,
)
from vision_doctor.ui.report_panel import build_report_downloads
from vision_doctor.ui.state import (
    REPORT_KEY,
    WORKSPACE_KEY,
    observe_upload,
    store_analysis,
)
from vision_doctor.ui.upload import (
    analyze_uploaded_bytes,
    build_ui_settings,
    safe_error_message,
)
from vision_doctor.utils.images import render_archive_preview


def _demo_bytes(tmp_path: Path) -> bytes:
    return generate_demo_zip(tmp_path / "demo.zip").read_bytes()


def test_streamlit_entry_imports_with_exactly_four_tab_contract() -> None:
    assert callable(app.main)
    assert list(TAB_LABELS) == [
        "Upload",
        "Dashboard",
        "Issue Explorer",
        "AI Doctor & Report",
    ]
    assert split_for_path("train/images/a.jpg") == "train"
    assert split_for_path("images/val/a.jpg") == "val"
    assert split_for_path("images/a.jpg") == "all"
    assert split_for_path("README.md") == "unknown"


def test_demo_upload_drives_offline_ui_data_and_downloads(tmp_path: Path) -> None:
    base = Settings(_env_file=None)
    settings = build_ui_settings(
        base,
        min_dimension=300,
        blur_threshold=75.0,
        dark_threshold=40.0,
        bright_threshold=215.0,
        near_duplicate_distance=4,
        allow_llm=False,
    )

    report, workspace = analyze_uploaded_bytes(
        _demo_bytes(tmp_path),
        "demo.zip",
        settings=settings,
    )
    try:
        assert report.diagnosis is not None
        assert report.diagnosis.generated_by == "deterministic"
        assert report.threshold_snapshot["image_quality"]["min_width"] == 300

        bbox_issues = filter_issues(report, codes={"BBOX_TINY"})
        quality_issues = filter_issues(report, codes={"IMAGE_BLURRY"})
        class_issues = filter_issues(report, class_ids={0})
        assert bbox_issues
        assert quality_issues
        assert class_issues
        assert report.duplicate_groups
        assert {group.kind for group in report.duplicate_groups} == {"exact", "near"}

        bbox_image = image_for_issue(report, bbox_issues[0])
        assert bbox_image is not None
        assert 0 in class_ids_for_issue(report, bbox_issues[0])
        assert split_for_path(bbox_image.relative_path) == "train"
        preview = render_archive_preview(
            workspace.archive_path,
            bbox_image.relative_path,
            bboxes=[bbox_issues[0].bbox],
        )
        assert preview is not None
        assert preview.startswith(b"\x89PNG\r\n\x1a\n")

        json_payload, html_payload = build_report_downloads(report)
        restored = AuditReport.model_validate(json.loads(json_payload))
        assert restored == report
        assert html_payload.startswith(b"<!doctype html>")
        assert len(json_payload) > 100
        assert len(html_payload) > 100
    finally:
        workspace.cleanup()
    assert not workspace.root.exists()


def test_new_upload_cleans_previous_session_workspace(tmp_path: Path) -> None:
    report, workspace = analyze_uploaded_bytes(
        _demo_bytes(tmp_path),
        "demo.zip",
        settings=Settings(_env_file=None),
    )
    state: dict[str, object] = {}
    observe_upload(state, "first-upload")
    store_analysis(state, report, workspace)
    old_root = workspace.root
    assert old_root.exists()

    observe_upload(state, "second-upload")

    assert not old_root.exists()
    assert state[REPORT_KEY] is None
    assert state[WORKSPACE_KEY] is None


def test_ui_error_text_does_not_expose_unexpected_exception_details() -> None:
    secret = "test-key-must-not-leak"

    message = safe_error_message(RuntimeError(f"provider failed with {secret}"))

    assert secret not in message
    assert "stack" not in message.lower()


def test_ui_preserves_actionable_parser_error_without_generic_masking() -> None:
    message = safe_error_message(
        DatasetParseError("data.yaml is missing required field 'names'.")
    )

    assert message == "data.yaml is missing required field 'names'."
    assert "Analysis could not be completed" not in message
