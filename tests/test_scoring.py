"""Tests for bounded, stable, and explainable health scoring."""

from __future__ import annotations

from vision_doctor.models import (
    DatasetManifest,
    DatasetSummary,
    DistributionStats,
    DuplicateGroup,
    ImageRecord,
    Issue,
    Severity,
)
from vision_doctor.scoring import (
    LEGACY_V1_PROFILE,
    PENALTY_CAPS,
    calculate_health_score,
)


def _manifest(*, class_count: int = 1, annotations: int = 0) -> DatasetManifest:
    image = ImageRecord(
        image_id="images/a.png",
        relative_path="images/a.png",
        width=400,
        height=400,
        file_size_bytes=100,
    )
    return DatasetManifest(
        dataset_name="score",
        source_archive="score.zip",
        images=[image],
        class_names={class_id: f"class-{class_id}" for class_id in range(class_count)},
        summary=DatasetSummary(
            image_count=1,
            label_file_count=1,
            annotation_count=annotations,
            class_count=class_count,
        ),
    )


def _distribution(*, classes: int = 1, all_zero: bool = False) -> DistributionStats:
    counts = {class_id: 0 if all_zero else 1 for class_id in range(classes)}
    total = sum(counts.values())
    zero_ids = [class_id for class_id, count in counts.items() if count == 0]
    return DistributionStats(
        total_annotations=total,
        class_counts=counts,
        class_percentages={
            class_id: count / total if total else 0.0
            for class_id, count in counts.items()
        },
        imbalance_ratio=None if all_zero else 1.0,
        imbalance_index=None if all_zero else 1.0,
        missing_class_ids=zero_ids,
        zero_instance_class_ids=zero_ids,
    )


def _issue(code: str, *, image_id: str = "images/a.png") -> Issue:
    return Issue(
        issue_id=f"issue-{code.lower()}",
        code=code,
        severity=Severity.WARNING,
        message=code,
        relative_path=image_id,
        image_id=image_id,
    )


def test_clean_single_class_scores_100_and_empty_label_does_not_deduct() -> None:
    manifest = _manifest()
    empty = _issue("LABEL_EMPTY")

    score = calculate_health_score(
        manifest,
        [empty],
        [],
        _distribution(),
    )

    assert score.overall == 100.0
    assert score.grade == "A"
    assert score.penalties == {category: 0.0 for category in PENALTY_CAPS}
    assert score.raw_ratios["distribution"] == 0.0
    assert any("LABEL_EMPTY" in line for line in score.explanation)
    assert score.profile_name == "legacy-v1"
    assert score.methodology_version == "1.0.0"
    assert score.penalty_caps == PENALTY_CAPS
    assert score.scoring_rules["label_empty_penalty"] is False
    assert score.scoring_rules["distribution_imbalance_normalizer"] == 9.0
    assert score.calibration_metadata["label_empty_penalty"] is False
    assert score.limitations


def test_each_category_is_capped_and_total_never_falls_below_zero() -> None:
    manifest = _manifest(class_count=2)
    issues = [
        _issue("LABEL_MISSING"),
        _issue("BBOX_OUT_OF_RANGE"),
        _issue("IMAGE_DARK"),
        _issue("LABEL_EMPTY"),
    ]
    duplicate = DuplicateGroup(
        group_id="duplicate",
        kind="exact",
        image_ids=["images/a.png", "images/b.png"],
        representative_image_id="images/a.png",
        hamming_distance=0,
    )

    first = calculate_health_score(
        manifest,
        issues,
        [duplicate],
        _distribution(classes=2, all_zero=True),
    )
    second = calculate_health_score(
        manifest,
        issues,
        [duplicate],
        _distribution(classes=2, all_zero=True),
    )

    assert first.overall == 0.0
    assert first.grade == "F"
    assert first.penalties == PENALTY_CAPS
    assert all(0.0 <= ratio <= 1.0 for ratio in first.raw_ratios.values())
    assert first == second
    assert len(first.breakdown) == 5


def test_explicit_legacy_profile_reproduces_default_numeric_behavior() -> None:
    manifest = _manifest(class_count=2, annotations=3)
    issues = [_issue("LABEL_MISSING"), _issue("BBOX_TINY")]
    distribution = _distribution(classes=2)

    default_score = calculate_health_score(manifest, issues, [], distribution)
    explicit_score = calculate_health_score(
        manifest,
        issues,
        [],
        distribution,
        profile=LEGACY_V1_PROFILE,
    )

    assert explicit_score == default_score
