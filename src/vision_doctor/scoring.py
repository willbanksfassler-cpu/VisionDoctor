"""Deterministic, versioned, and explainable VisionDoctor health scoring."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from vision_doctor.config import ScoringConfig
from vision_doctor.models import (
    DatasetManifest,
    DistributionStats,
    DuplicateGroup,
    HealthScore,
    Issue,
    ScoreBreakdown,
)

SCORE_CATEGORIES = (
    "structural",
    "bbox",
    "image",
    "duplicates",
    "distribution",
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


class ScoreProfile(BaseModel):
    """Immutable scoring rules and their evidence boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_name: Literal["legacy-v1", "calibrated-v2"]
    methodology_version: str = Field(min_length=1)
    penalty_caps: dict[str, float]
    category_issue_codes: dict[str, frozenset[str]]
    distribution_imbalance_normalizer: float = Field(gt=0.0)
    label_empty_penalty: bool = False
    calibration_metadata: dict[str, JsonValue]
    limitations: tuple[str, ...]

    @model_validator(mode="after")
    def validate_caps(self) -> ScoreProfile:
        if set(self.penalty_caps) != set(SCORE_CATEGORIES):
            raise ValueError("score profile must define every penalty category")
        if any(cap < 0.0 or cap > 100.0 for cap in self.penalty_caps.values()):
            raise ValueError("score profile penalty caps must be in [0, 100]")
        if sum(self.penalty_caps.values()) > 100.0:
            raise ValueError("score profile penalty caps must total at most 100")
        if set(self.category_issue_codes) != {"structural", "bbox", "image"}:
            raise ValueError(
                "score profile must define structural, bbox, and image issue rules"
            )
        return self


LEGACY_V1_PROFILE = ScoreProfile(
    profile_name="legacy-v1",
    methodology_version="1.0.0",
    penalty_caps=PENALTY_CAPS,
    category_issue_codes={
        "structural": frozenset(STRUCTURAL_CODES),
        "bbox": frozenset(BBOX_CODES),
        "image": frozenset(IMAGE_CODES),
    },
    distribution_imbalance_normalizer=9.0,
    label_empty_penalty=False,
    calibration_metadata={
        "basis": "original_mvp_fixed_rules",
        "bbox_denominator": "valid_annotations_plus_bbox_issues",
        "distribution_imbalance_normalizer": 9.0,
        "label_empty_penalty": False,
        "benchmark_required": False,
    },
    limitations=(
        "The score covers only implemented deterministic checks and configured thresholds.",
        "It is not calibrated against real business outcomes or model performance.",
        "Statistical bbox outliers and split-leakage candidates are evidence but are not automatically penalized in legacy-v1.",
    ),
)


def calibrated_v2_candidate(
    penalty_caps: dict[str, float],
    calibration_metadata: dict[str, JsonValue],
) -> ScoreProfile:
    """Build an experimental v2 candidate without enabling it in production."""

    return ScoreProfile(
        profile_name="calibrated-v2",
        methodology_version="2.0.0-candidate",
        penalty_caps=penalty_caps,
        category_issue_codes=LEGACY_V1_PROFILE.category_issue_codes,
        distribution_imbalance_normalizer=9.0,
        label_empty_penalty=False,
        calibration_metadata=calibration_metadata,
        limitations=(
            "This candidate is derived from controlled synthetic corruption data.",
            "Independent real-domain calibration is still required before business use.",
            "The score is not a prediction of mAP, training quality, or repair success.",
        ),
    )


def score_profile_from_config(config: ScoringConfig) -> ScoreProfile:
    """Resolve the validated application configuration to one score profile."""

    if config.profile_name == "legacy-v1":
        return LEGACY_V1_PROFILE
    return ScoreProfile(
        profile_name="calibrated-v2",
        methodology_version="2.0.0",
        penalty_caps=config.calibrated_v2_penalty_caps,
        category_issue_codes=LEGACY_V1_PROFILE.category_issue_codes,
        distribution_imbalance_normalizer=9.0,
        label_empty_penalty=False,
        calibration_metadata=config.calibration_metadata,
        limitations=(
            "Calibrated only under the benchmark evidence recorded in calibration_metadata.",
            "Real-domain performance and downstream model gains remain unverified.",
            "The score is a data-quality heuristic, not a model-performance prediction.",
        ),
    )


def score_profile_from_health_score(score: HealthScore) -> ScoreProfile:
    """Reconstruct the immutable profile recorded in a prior score."""

    if score.profile_name == "legacy-v1":
        return LEGACY_V1_PROFILE
    return ScoreProfile(
        profile_name="calibrated-v2",
        methodology_version=score.methodology_version,
        penalty_caps=score.penalty_caps,
        category_issue_codes={
            category: frozenset(
                score.scoring_rules.get("category_issue_codes", {}).get(
                    category,
                    LEGACY_V1_PROFILE.category_issue_codes[category],
                )
            )
            for category in ("structural", "bbox", "image")
        },
        distribution_imbalance_normalizer=float(
            score.scoring_rules.get("distribution_imbalance_normalizer", 9.0)
        ),
        label_empty_penalty=bool(
            score.scoring_rules.get("label_empty_penalty", False)
        ),
        calibration_metadata=score.calibration_metadata,
        limitations=tuple(score.limitations),
    )


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
    *,
    profile: ScoreProfile | None = None,
) -> HealthScore:
    """Calculate a bounded score from five transparent risk proportions."""

    active = profile or LEGACY_V1_PROFILE
    structural_codes = set(active.category_issue_codes["structural"])
    if active.label_empty_penalty:
        structural_codes.add("LABEL_EMPTY")
    structural_issues = [issue for issue in issues if issue.code in structural_codes]
    bbox_issues = [
        issue
        for issue in issues
        if issue.code in active.category_issue_codes["bbox"]
    ]
    image_issues = [
        issue
        for issue in issues
        if issue.code in active.category_issue_codes["image"]
    ]

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
        imbalance_ratio = min(
            max(
                (imbalance_index - 1.0)
                / active.distribution_imbalance_normalizer,
                0.0,
            ),
            1.0,
        )
        distribution_ratio = max(zero_ratio, rare_ratio, imbalance_ratio)

    raw_ratios = {
        "structural": structural_ratio,
        "bbox": bbox_ratio,
        "image": image_ratio,
        "duplicates": duplicate_ratio,
        "distribution": distribution_ratio,
    }
    penalties = {
        category: round(active.penalty_caps[category] * ratio, 4)
        for category, ratio in raw_ratios.items()
    }
    overall = round(min(max(100.0 - sum(penalties.values()), 0.0), 100.0), 2)
    explanation = [
        (
            f"{category}: ratio {raw_ratios[category]:.4f} × cap "
            f"{active.penalty_caps[category]:.0f} = penalty "
            f"{penalties[category]:.4f}."
        )
        for category in SCORE_CATEGORIES
    ]
    if not active.label_empty_penalty:
        explanation.append(
            "LABEL_EMPTY is informational and never contributes to a penalty."
        )
    breakdown = [
        ScoreBreakdown(
            component=category,
            score=round(100.0 * (1.0 - raw_ratios[category]), 4),
            weight=active.penalty_caps[category] / 100.0,
            deductions=[explanation[index]],
        )
        for index, category in enumerate(SCORE_CATEGORIES)
    ]
    return HealthScore(
        overall=overall,
        grade=_grade(overall),
        penalties=penalties,
        raw_ratios=raw_ratios,
        explanation=explanation,
        breakdown=breakdown,
        methodology_version=active.methodology_version,
        profile_name=active.profile_name,
        penalty_caps=dict(active.penalty_caps),
        scoring_rules={
            "category_issue_codes": {
                category: sorted(codes)
                for category, codes in active.category_issue_codes.items()
            },
            "distribution_imbalance_normalizer": (
                active.distribution_imbalance_normalizer
            ),
            "label_empty_penalty": active.label_empty_penalty,
        },
        calibration_metadata=dict(active.calibration_metadata),
        limitations=list(active.limitations),
    )
