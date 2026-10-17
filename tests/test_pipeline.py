"""End-to-end tests for deterministic demo generation and the core pipeline."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from scripts.generate_demo_dataset import generate_demo_zip
from vision_doctor.config import Settings
from vision_doctor.models import AuditReport
from vision_doctor.parser import DatasetParseError
from vision_doctor.pipeline import run_pipeline

EXPECTED_DEMO_CODES = {
    "LABEL_MISSING",
    "LABEL_ORPHAN",
    "LABEL_EMPTY",
    "LABEL_PARSE_ERROR",
    "CLASS_ID_INVALID",
    "BBOX_OUT_OF_RANGE",
    "BBOX_TINY",
    "IMAGE_UNREADABLE",
    "IMAGE_BLURRY",
    "IMAGE_DARK",
    "IMAGE_BRIGHT",
    "IMAGE_LOW_RESOLUTION",
}


def test_demo_is_reproducible_and_pipeline_returns_valid_report(tmp_path: Path) -> None:
    first_archive = generate_demo_zip(tmp_path / "first.zip")
    second_archive = generate_demo_zip(tmp_path / "second.zip")

    assert first_archive.read_bytes() == second_archive.read_bytes()

    report = run_pipeline(first_archive, temp_root=tmp_path)
    serialized = report.model_dump_json()
    restored = AuditReport.model_validate_json(serialized)
    actual_codes = {issue.code for issue in report.issues}

    assert EXPECTED_DEMO_CODES <= actual_codes
    assert {group.kind for group in report.duplicate_groups} == {"exact", "near"}
    assert report.manifest.summary.issue_count == len(report.issues)
    assert 0.0 <= report.health_score.overall <= 100.0
    assert report.health_score.grade in {"A", "B", "C", "D", "F"}
    assert report.health_score == restored.health_score
    assert report.threshold_snapshot == restored.threshold_snapshot
    assert report.threshold_snapshot["image_quality"]["blur_variance_threshold"] == 80.0
    assert (
        report.threshold_snapshot["duplicate_detection"]
        ["near_duplicate_hamming_threshold"]
        == 4
    )
    assert report.diagnosis is None

    repeated = run_pipeline(second_archive, temp_root=tmp_path)
    assert repeated.health_score == report.health_score
    assert [issue.code for issue in repeated.issues] == [
        issue.code for issue in report.issues
    ]


def test_pipeline_preserves_readable_structural_error(tmp_path: Path) -> None:
    archive = tmp_path / "missing-data-yaml.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("images/a.png", b"not relevant")
        output.writestr("labels/a.txt", b"")

    with pytest.raises(DatasetParseError, match="contain data.yaml"):
        run_pipeline(archive, temp_root=tmp_path)


def test_pipeline_can_attach_no_key_fallback_diagnosis(tmp_path: Path) -> None:
    archive = generate_demo_zip(tmp_path / "demo.zip")

    report = run_pipeline(
        archive,
        settings=Settings(_env_file=None),
        temp_root=tmp_path,
        run_doctor=True,
    )

    assert report.diagnosis is not None
    assert report.diagnosis.generated_by == "deterministic"
