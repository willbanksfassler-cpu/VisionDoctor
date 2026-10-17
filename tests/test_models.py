"""Construction and rejection tests for the public data contracts."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from vision_doctor.models import (
    AnnotationRecord,
    AuditReport,
    BoundingBox,
    DatasetManifest,
    DatasetSummary,
    Diagnosis,
    DistributionStats,
    DuplicateGroup,
    HealthScore,
    ImageRecord,
    Issue,
    PriorityFinding,
    RecommendedAction,
    ScoreBreakdown,
    Severity,
)


def build_valid_report() -> AuditReport:
    bbox = BoundingBox.model_validate([0.5, 0.5, 0.4, 0.2])
    annotation = AnnotationRecord(
        image_id="image-1",
        class_id=0,
        bbox=bbox,
        source_path="labels/image-1.txt",
        line_number=1,
    )
    image = ImageRecord(
        image_id="image-1",
        relative_path="images/image-1.jpg",
        width=640,
        height=480,
        file_size_bytes=12_345,
        annotation_count=1,
        sha256="a" * 64,
    )
    summary = DatasetSummary(
        image_count=1,
        label_file_count=1,
        annotation_count=1,
        class_count=1,
        issue_count=1,
        total_size_bytes=12_345,
    )
    manifest = DatasetManifest(
        dataset_name="fixture",
        source_archive="fixture.zip",
        images=[image],
        annotations=[annotation],
        class_names={0: "object"},
        summary=summary,
    )
    issue = Issue(
        issue_id="issue-1",
        code="image.too_small",
        severity=Severity.WARNING,
        message="Image is below the recommended dimensions.",
        relative_path=image.relative_path,
        image_id=image.image_id,
        evidence={"width": image.width, "height": image.height},
    )
    duplicate_group = DuplicateGroup(
        group_id="duplicate-1",
        kind="near",
        image_ids=["image-1", "image-2"],
        hamming_distance=2,
    )
    distribution = DistributionStats(
        total_annotations=1,
        class_counts={0: 1},
        class_percentages={0: 1.0},
        imbalance_ratio=1.0,
    )
    breakdown = ScoreBreakdown(
        component="annotations",
        score=90.0,
        weight=1.0,
        deductions=["One warning"],
    )
    health_score = HealthScore(overall=90.0, breakdown=[breakdown])
    finding = PriorityFinding(
        rank=1,
        title="Review small images",
        rationale="Small images may hide relevant visual detail.",
        severity=Severity.WARNING,
        issue_ids=[issue.issue_id],
    )
    action = RecommendedAction(
        action_id="action-1",
        priority=1,
        title="Review source resolution",
        description="Inspect the source asset before deciding whether to replace it.",
        related_issue_ids=[issue.issue_id],
        estimated_effort="low",
    )
    diagnosis = Diagnosis(
        generated_by="deterministic",
        summary="One warning requires review.",
        priority_findings=[finding],
        recommended_actions=[action],
        caveats=["No source files were modified."],
    )
    return AuditReport(
        report_id="report-1",
        generated_at=datetime.now().astimezone(),
        manifest=manifest,
        issues=[issue],
        duplicate_groups=[duplicate_group],
        distribution=distribution,
        health_score=health_score,
        diagnosis=diagnosis,
    )


def test_all_core_models_construct_and_report_serializes() -> None:
    report = build_valid_report()

    assert report.schema_version == "1.0.0"
    assert report.manifest.annotations[0].bbox.width == pytest.approx(0.4)
    assert report.issues[0].severity is Severity.WARNING
    assert report.model_dump(mode="json")["schema_version"] == "1.0.0"


def test_invalid_severity_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Issue(code="bad", severity="urgent", message="Invalid severity")


@pytest.mark.parametrize("score", [-0.01, 100.01])
def test_invalid_health_score_is_rejected(score: float) -> None:
    breakdown = ScoreBreakdown(component="annotations", score=80, weight=1)

    with pytest.raises(ValidationError):
        HealthScore(overall=score, breakdown=[breakdown])


def test_wrong_bbox_length_is_rejected() -> None:
    with pytest.raises(ValidationError):
        BoundingBox.model_validate([0.5, 0.5, 0.2])


def test_bbox_outside_image_bounds_is_rejected() -> None:
    with pytest.raises(ValidationError):
        BoundingBox.model_validate([0.05, 0.5, 0.2, 0.2])


def test_naive_report_timestamp_is_rejected() -> None:
    report_data = build_valid_report().model_dump()
    report_data["generated_at"] = datetime(2026, 1, 1)

    with pytest.raises(ValidationError):
        AuditReport.model_validate(report_data)
