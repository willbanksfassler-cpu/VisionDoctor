"""Tests for class-conditional bounding-box statistical candidates."""

from __future__ import annotations

from vision_doctor.checkers.bbox_outliers import (
    BBOX_AREA_OUTLIER,
    BBOX_ASPECT_RATIO_OUTLIER,
    check_bbox_outliers,
)
from vision_doctor.config import BBoxOutlierConfig
from vision_doctor.models import (
    AnnotationRecord,
    BoundingBox,
    DatasetManifest,
    DatasetSummary,
    Severity,
)


def _annotation(
    index: int,
    class_id: int,
    width: float,
    height: float,
) -> AnnotationRecord:
    return AnnotationRecord(
        image_id=f"train/images/{index:02d}.jpg",
        class_id=class_id,
        bbox=BoundingBox.model_validate([0.5, 0.5, width, height]),
        source_path=f"train/labels/{index:02d}.txt",
        line_number=1,
    )


def _manifest(annotations: list[AnnotationRecord]) -> DatasetManifest:
    return DatasetManifest(
        dataset_name="bbox-statistics",
        source_archive="bbox-statistics.zip",
        annotations=annotations,
        class_names={0: "regular", 1: "small-object"},
        summary=DatasetSummary(
            image_count=len(annotations),
            label_file_count=len(annotations),
            annotation_count=len(annotations),
            class_count=2,
        ),
    )


def test_area_and_aspect_outliers_include_explainable_class_statistics() -> None:
    annotations = [
        _annotation(index, 0, 0.2, 0.2) for index in range(12)
    ] + [
        _annotation(12, 0, 0.04, 0.04),
        _annotation(13, 0, 0.5, 0.1),
    ]

    issues = check_bbox_outliers(_manifest(annotations))
    by_code = {issue.code: issue for issue in issues}

    assert set(by_code) == {BBOX_AREA_OUTLIER, BBOX_ASPECT_RATIO_OUTLIER}
    assert by_code[BBOX_AREA_OUTLIER].relative_path == "train/labels/12.txt"
    assert (
        by_code[BBOX_ASPECT_RATIO_OUTLIER].relative_path
        == "train/labels/13.txt"
    )
    for issue in issues:
        assert issue.severity is Severity.WARNING
        assert issue.annotation_line == 1
        assert issue.metrics["class_id"] == 0
        assert issue.metrics["sample_count"] == 14
        assert issue.metrics["median"] > 0
        assert issue.metrics["outlier_score"] >= issue.metrics["outlier_threshold"]
        assert issue.metrics["requires_human_confirmation"] is True


def test_small_legitimate_class_is_modeled_separately_without_false_positive() -> None:
    annotations = [
        _annotation(index, 0, 0.2, 0.2) for index in range(10)
    ] + [
        _annotation(index + 10, 1, 0.02, 0.02) for index in range(10)
    ]

    issues = check_bbox_outliers(_manifest(annotations))

    assert issues == []


def test_insufficient_class_samples_do_not_create_outlier_claims() -> None:
    annotations = [
        _annotation(index, 0, 0.2, 0.2) for index in range(4)
    ] + [
        _annotation(4, 0, 0.01, 0.01)
    ]
    config = BBoxOutlierConfig(min_samples_per_class=10)

    assert check_bbox_outliers(_manifest(annotations), config=config) == []
