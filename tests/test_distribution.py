"""Tests for class instance, image coverage, rarity, and imbalance statistics."""

from __future__ import annotations

import pytest

from vision_doctor.checkers.distribution import calculate_distribution
from vision_doctor.models import (
    AnnotationRecord,
    BoundingBox,
    DatasetManifest,
    DatasetSummary,
)


def _annotation(image_id: str, class_id: int, line: int) -> AnnotationRecord:
    return AnnotationRecord(
        image_id=image_id,
        class_id=class_id,
        bbox=BoundingBox.model_validate([0.5, 0.5, 0.2, 0.2]),
        source_path=f"labels/{image_id}.txt",
        line_number=line,
    )


def _manifest(
    class_names: dict[int, str], annotations: list[AnnotationRecord]
) -> DatasetManifest:
    return DatasetManifest(
        dataset_name="distribution",
        source_archive="distribution.zip",
        class_names=class_names,
        annotations=annotations,
        summary=DatasetSummary(
            image_count=len({item.image_id for item in annotations}),
            label_file_count=0,
            annotation_count=len(annotations),
            class_count=len(class_names),
        ),
    )


def test_distribution_counts_coverage_zero_rare_and_imbalance() -> None:
    annotations = [
        _annotation("image-a", 0, line) for line in range(1, 11)
    ] + [
        _annotation("image-b", 0, line) for line in range(1, 11)
    ] + [
        _annotation("image-a" if line == 1 else "image-c", 1, line)
        for line in range(1, 4)
    ]

    stats = calculate_distribution(
        _manifest({0: "common", 1: "rare", 2: "absent"}, annotations)
    )

    assert stats.total_annotations == 23
    assert stats.class_counts == {0: 20, 1: 3, 2: 0}
    assert stats.class_image_counts == {0: 2, 1: 2, 2: 0}
    assert stats.class_percentages[0] == pytest.approx(20 / 23)
    assert stats.zero_instance_class_ids == [2]
    assert stats.missing_class_ids == [2]
    assert stats.rare_class_threshold == 10
    assert stats.rare_class_ids == [1]
    assert stats.imbalance_index == pytest.approx(20 / 3)


def test_single_class_is_not_marked_imbalanced() -> None:
    stats = calculate_distribution(
        _manifest({0: "only"}, [_annotation("image-a", 0, 1)])
    )

    assert stats.imbalance_index == 1.0
    assert stats.imbalance_ratio == 1.0
    assert stats.zero_instance_class_ids == []


def test_all_classes_can_have_zero_instances() -> None:
    stats = calculate_distribution(_manifest({0: "cat", 1: "dog"}, []))

    assert stats.class_counts == {0: 0, 1: 0}
    assert stats.class_image_counts == {0: 0, 1: 0}
    assert stats.zero_instance_class_ids == [0, 1]
    assert stats.rare_class_ids == []
    assert stats.imbalance_index is None
