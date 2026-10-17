"""Deterministic and explainable VisionDoctor health scoring."""

from __future__ import annotations

from collections.abc import Iterable

from vision_doctor.models import (
    DatasetManifest,
    DistributionStats,
    DuplicateGroup,
    HealthScore,
    Issue,
    ScoreBreakdown,
)

PENALTY_CAPS = {
    "structural": 25.0,
    "bbox": 20.0,
    "image": 20.0,
    "duplicates": 15.0,
    "distribution": 20.0,
}

STRUCTURAL_CODES = {
    "LABEL_MISSING",
    "LABEL_ORPHAN",
    "LABEL_PARSE_ERROR",
    "CLASS_ID_INVALID",
}
BBOX_CODES = {
    "BBOX_NON_POSITIVE",
    "BBOX_OUT_OF_RANGE",
    "BBOX_CROSSES_BORDER",
    "BBOX_TINY",
}
IMAGE_CODES = {
    "IMAGE_UNREADABLE",
    "IMAGE_BLURRY",
    "IMAGE_DARK",
    "IMAGE_BRIGHT",
    "IMAGE_LOW_RESOLUTION",
}


def _bounded_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return min(max(float(numerator) / float(denominator), 0.0), 1.0)


def _affected_items(issues: Iterable[Issue]) -> int:
    identities = {
        issue.image_id or issue.relative_path or issue.issue_id for issue in issues
    }
    return len(identities)


def _grade(score: float) -> str:
    if score >= 90.0:
        return "A"
    if score >= 80.0:
        return "B"
    if score >= 70.0:
        return "C"
    if score >= 60.0:
        return "D"
    return "F"


def calculate_health_score(
    manifest: DatasetManifest,
    issues: list[Issue],
    duplicate_groups: list[DuplicateGroup],
    distribution: DistributionStats,
) -> HealthScore:
    """Calculate a bounded score from five transparent risk proportions."""

    structural_issues = [issue for issue in issues if issue.code in STRUCTURAL_CODES]
    bbox_issues = [issue for issue in issues if issue.code in BBOX_CODES]
    image_issues = [issue for issue in issues if issue.code in IMAGE_CODES]

    structural_ratio = _bounded_ratio(
        _affected_items(structural_issues), manifest.summary.image_count
    )
    bbox_population = manifest.summary.annotation_count + len(bbox_issues)
    bbox_ratio = _bounded_ratio(len(bbox_issues), bbox_population)
    image_ratio = _bounded_ratio(
        _affected_items(image_issues), manifest.summary.image_count
    )
    duplicate_image_ids = {
        image_id for group in duplicate_groups for image_id in group.image_ids
    }
    duplicate_ratio = _bounded_ratio(
        len(duplicate_image_ids), manifest.summary.image_count
    )

    class_count = len(distribution.class_counts)
    if class_count <= 1:
        distribution_ratio = 0.0
    else:
        zero_ratio = _bounded_ratio(
            len(distribution.zero_instance_class_ids), class_count
        )
        rare_ratio = _bounded_ratio(len(distribution.rare_class_ids), class_count)
        imbalance_index = distribution.imbalance_index or 1.0
        imbalance_ratio = min(max((imbalance_index - 1.0) / 9.0, 0.0), 1.0)
        distribution_ratio = max(zero_ratio, rare_ratio, imbalance_ratio)

    raw_ratios = {
        "structural": structural_ratio,
        "bbox": bbox_ratio,
        "image": image_ratio,
        "duplicates": duplicate_ratio,
        "distribution": distribution_ratio,
    }
    penalties = {
        category: round(PENALTY_CAPS[category] * ratio, 4)
        for category, ratio in raw_ratios.items()
    }
    overall = round(min(max(100.0 - sum(penalties.values()), 0.0), 100.0), 2)
    explanation = [
        (
            f"{category}: ratio {raw_ratios[category]:.4f} × cap "
            f"{PENALTY_CAPS[category]:.0f} = penalty {penalties[category]:.4f}."
        )
        for category in PENALTY_CAPS
    ]
    explanation.append(
        "LABEL_EMPTY is informational and never contributes to a penalty."
    )
    breakdown = [
        ScoreBreakdown(
            component=category,
            score=round(100.0 * (1.0 - raw_ratios[category]), 4),
            weight=PENALTY_CAPS[category] / 100.0,
            deductions=[explanation[index]],
        )
        for index, category in enumerate(PENALTY_CAPS)
    ]
    return HealthScore(
        overall=overall,
        grade=_grade(overall),
        penalties=penalties,
        raw_ratios=raw_ratios,
        explanation=explanation,
        breakdown=breakdown,
        methodology_version="1.0.0",
    )
