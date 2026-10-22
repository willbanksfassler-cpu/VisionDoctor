"""Synthetic benchmark evaluation for versioned Health Score candidates."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from vision_doctor.evaluation import BenchmarkResult
from vision_doctor.models import (
    DatasetManifest,
    DatasetSummary,
    DistributionStats,
    DuplicateGroup,
    Issue,
    Severity,
)
from vision_doctor.scoring import (
    LEGACY_V1_PROFILE,
    ScoreProfile,
    calculate_health_score,
    calibrated_v2_candidate,
)


class CalibrationContract(BaseModel):
    """Strict base for stable calibration output."""

    model_config = ConfigDict(extra="forbid")


class MonotonicityCheck(CalibrationContract):
    """One deterministic score invariant."""

    name: str
    passed: bool
    observed: dict[str, float | bool]
    rule: str


class MonotonicityReport(CalibrationContract):
    """All invariants evaluated for one profile."""

    profile_name: str
    checks: list[MonotonicityCheck]
    passed: bool


class CandidateCalibration(CalibrationContract):
    """One candidate's synthetic suitability evidence."""

    candidate_name: str
    profile_name: Literal["legacy-v1", "calibrated-v2"]
    penalty_caps: dict[str, float]
    monotonicity: MonotonicityReport
    clean_score: float
    mild_score: float
    severe_score: float
    discrimination: float = Field(ge=0.0, le=100.0)
    stability_delta: float = Field(ge=0.0, le=100.0)
    acceptance_conditions: dict[str, bool]
    accepted: bool


class ScoreCalibrationReport(CalibrationContract):
    """Non-mutating assessment of score-profile candidates."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    benchmark_profile: Literal["quick", "standard", "scale"]
    benchmark_seed: int
    candidates: list[CandidateCalibration]
    recommended_candidate: str | None
    production_configuration_modified: Literal[False] = False
    limitations: list[str]


def _manifest(*, class_count: int = 2) -> DatasetManifest:
    return DatasetManifest(
        dataset_name="score-calibration",
        source_archive="synthetic.zip",
        class_names={index: f"class-{index}" for index in range(class_count)},
        summary=DatasetSummary(
            image_count=10,
            label_file_count=10,
            annotation_count=10,
            class_count=class_count,
        ),
    )


def _distribution(*, severe: bool = False, class_count: int = 2) -> DistributionStats:
    if class_count == 1:
        counts = {0: 10}
    elif severe:
        counts = {0: 10, 1: 0}
    else:
        counts = {0: 5, 1: 5}
    total = sum(counts.values())
    zero = [class_id for class_id, count in counts.items() if count == 0]
    return DistributionStats(
        total_annotations=total,
        class_counts=counts,
        class_image_counts=counts,
        class_percentages={
            class_id: count / total if total else 0.0
            for class_id, count in counts.items()
        },
        imbalance_ratio=10.0 if severe else 1.0,
        imbalance_index=10.0 if severe else 1.0,
        rare_class_ids=zero,
        missing_class_ids=zero,
        zero_instance_class_ids=zero,
    )


def _issues(code: str, count: int, *, severity: Severity = Severity.WARNING) -> list[Issue]:
    return [
        Issue(
            issue_id=f"{code.lower()}-{index}",
            code=code,
            severity=severity,
            message=code,
            relative_path=f"train/images/{index}.jpg",
            image_id=f"train/images/{index}.jpg",
        )
        for index in range(count)
    ]


def _duplicates(image_count: int) -> list[DuplicateGroup]:
    if image_count < 2:
        return []
    return [
        DuplicateGroup(
            group_id=f"duplicates-{image_count}",
            kind="exact",
            image_ids=[f"train/images/{index}.jpg" for index in range(image_count)],
            representative_image_id="train/images/0.jpg",
            hamming_distance=0,
        )
    ]


def _score(
    profile: ScoreProfile,
    *,
    issues: list[Issue] | None = None,
    duplicate_count: int = 0,
    severe_distribution: bool = False,
    class_count: int = 2,
) -> float:
    return calculate_health_score(
        _manifest(class_count=class_count),
        issues or [],
        _duplicates(duplicate_count),
        _distribution(severe=severe_distribution, class_count=class_count),
        profile=profile,
    ).overall


def validate_score_monotonicity(profile: ScoreProfile) -> MonotonicityReport:
    """Exercise score invariants using fixed, fully synthetic scenarios."""

    checks: list[MonotonicityCheck] = []

    def compare_more(code: str, name: str) -> None:
        one = _score(profile, issues=_issues(code, 1))
        two = _score(profile, issues=_issues(code, 2))
        checks.append(
            MonotonicityCheck(
                name=name,
                passed=two <= one,
                observed={"one_issue": one, "two_issues": two},
                rule="Adding another effective issue of the same category cannot raise the score.",
            )
        )

    compare_more("LABEL_MISSING", "structural_issue_monotonicity")
    compare_more("BBOX_OUT_OF_RANGE", "bbox_issue_monotonicity")
    compare_more("IMAGE_DARK", "image_issue_monotonicity")

    two_duplicates = _score(profile, duplicate_count=2)
    four_duplicates = _score(profile, duplicate_count=4)
    checks.append(
        MonotonicityCheck(
            name="duplicate_monotonicity",
            passed=four_duplicates <= two_duplicates,
            observed={
                "two_duplicate_images": two_duplicates,
                "four_duplicate_images": four_duplicates,
            },
            rule="Increasing affected duplicate images cannot raise the score.",
        )
    )

    balanced = _score(profile)
    imbalanced = _score(profile, severe_distribution=True)
    checks.append(
        MonotonicityCheck(
            name="distribution_monotonicity",
            passed=imbalanced <= balanced,
            observed={"balanced": balanced, "severe_imbalance": imbalanced},
            rule="A more severe distribution ratio cannot raise the score.",
        )
    )

    info = _score(
        profile,
        issues=_issues("LABEL_EMPTY", 1, severity=Severity.INFO),
    )
    error = _score(
        profile,
        issues=_issues("LABEL_MISSING", 1, severity=Severity.ERROR),
    )
    checks.append(
        MonotonicityCheck(
            name="error_not_less_than_informational",
            passed=error <= info,
            observed={"info_score": info, "error_score": error},
            rule="A penalized error cannot deduct less than informational LABEL_EMPTY.",
        )
    )

    at_cap = _score(profile, issues=_issues("LABEL_MISSING", 10))
    beyond_cap = _score(profile, issues=_issues("LABEL_MISSING", 20))
    checks.append(
        MonotonicityCheck(
            name="category_cap_stability",
            passed=at_cap == beyond_cap and beyond_cap >= 0.0,
            observed={"at_cap": at_cap, "beyond_cap": beyond_cap},
            rule="After a category cap is reached, the score remains bounded and stable.",
        )
    )

    empty_label = _score(profile, issues=_issues("LABEL_EMPTY", 1))
    checks.append(
        MonotonicityCheck(
            name="empty_label_no_penalty",
            passed=empty_label == 100.0,
            observed={"score": empty_label},
            rule="An empty label remains an informational possible negative sample.",
        )
    )

    single_class = _score(profile, severe_distribution=True, class_count=1)
    checks.append(
        MonotonicityCheck(
            name="single_class_distribution_zero",
            passed=single_class == 100.0,
            observed={"score": single_class},
            rule="A single-class dataset has zero distribution penalty.",
        )
    )

    repeated_first = _score(profile, issues=_issues("IMAGE_DARK", 3))
    repeated_second = _score(profile, issues=_issues("IMAGE_DARK", 3))
    checks.append(
        MonotonicityCheck(
            name="deterministic_repeatability",
            passed=repeated_first == repeated_second,
            observed={"first": repeated_first, "second": repeated_second},
            rule="Repeated scoring of identical facts returns the same result.",
        )
    )
    return MonotonicityReport(
        profile_name=profile.profile_name,
        checks=checks,
        passed=all(check.passed for check in checks),
    )


def _candidate_profiles(benchmark: BenchmarkResult) -> list[tuple[str, ScoreProfile]]:
    metadata = {
        "benchmark_profile": benchmark.profile,
        "benchmark_schema_version": benchmark.schema_version,
        "benchmark_seed": benchmark.seed,
        "synthetic_only": True,
    }
    return [
        ("legacy-v1", LEGACY_V1_PROFILE),
        (
            "calibrated-v2-balanced",
            calibrated_v2_candidate(
                {
                    "structural": 27.0,
                    "bbox": 23.0,
                    "image": 20.0,
                    "duplicates": 12.0,
                    "distribution": 18.0,
                },
                {**metadata, "candidate_name": "balanced"},
            ),
        ),
        (
            "calibrated-v2-duplicate-aware",
            calibrated_v2_candidate(
                {
                    "structural": 25.0,
                    "bbox": 20.0,
                    "image": 18.0,
                    "duplicates": 19.0,
                    "distribution": 18.0,
                },
                {**metadata, "candidate_name": "duplicate-aware"},
            ),
        ),
    ]


def calibrate_score_profiles(benchmark: BenchmarkResult) -> ScoreCalibrationReport:
    """Assess candidates without changing runtime configuration or source files."""

    candidates: list[CandidateCalibration] = []
    for name, profile in _candidate_profiles(benchmark):
        monotonicity = validate_score_monotonicity(profile)
        clean = _score(profile)
        mild_issues = [
            *_issues("LABEL_MISSING", 1),
            *_issues("BBOX_OUT_OF_RANGE", 1),
            *_issues("IMAGE_DARK", 1),
        ]
        mild = _score(profile, issues=mild_issues, duplicate_count=2)
        severe_issues = [
            *_issues("LABEL_MISSING", 10),
            *_issues("BBOX_OUT_OF_RANGE", 20),
            *_issues("IMAGE_DARK", 10),
        ]
        severe = _score(
            profile,
            issues=severe_issues,
            duplicate_count=10,
            severe_distribution=True,
        )
        repeat = _score(
            profile,
            issues=severe_issues,
            duplicate_count=10,
            severe_distribution=True,
        )
        discrimination = round(clean - severe, 2)
        stability_delta = round(abs(severe - repeat), 6)
        conditions = {
            "standard_or_scale_profile": benchmark.profile in {"standard", "scale"},
            "micro_f1_at_least_0_95": (
                benchmark.evaluation.micro_average.f1 >= 0.95
            ),
            "macro_f1_at_least_0_95": (
                benchmark.evaluation.macro_average.f1 >= 0.95
            ),
            "no_unmatched_findings": not benchmark.evaluation.unmatched,
            "distribution_truth_matched": (
                benchmark.evaluation.distribution_matches_ground_truth
            ),
            "monotonicity_passed": monotonicity.passed,
            "discrimination_at_least_25": discrimination >= 25.0,
            "stability_exact": stability_delta == 0.0,
        }
        accepted = all(conditions.values())
        candidates.append(
            CandidateCalibration(
                candidate_name=name,
                profile_name=profile.profile_name,
                penalty_caps=profile.penalty_caps,
                monotonicity=monotonicity,
                clean_score=clean,
                mild_score=mild,
                severe_score=severe,
                discrimination=discrimination,
                stability_delta=stability_delta,
                acceptance_conditions=conditions,
                accepted=accepted,
            )
        )
    recommended = next(
        (
            item.candidate_name
            for item in candidates
            if item.profile_name == "calibrated-v2" and item.accepted
        ),
        None,
    )
    return ScoreCalibrationReport(
        benchmark_profile=benchmark.profile,
        benchmark_seed=benchmark.seed,
        candidates=candidates,
        recommended_candidate=recommended,
        limitations=[
            "The benchmark is synthetic controlled-corruption data, not real business validation.",
            "A quick profile is intentionally insufficient to recommend calibrated-v2.",
            "Calibration assesses score behavior, not mAP or downstream training outcomes.",
            "This tool never changes the production score configuration automatically.",
        ],
    )


def render_calibration_markdown(report: ScoreCalibrationReport) -> str:
    """Render a stable human-readable calibration summary."""

    lines = [
        "# VisionDoctor Health Score calibration",
        "",
        f"- Benchmark profile: `{report.benchmark_profile}`",
        f"- Benchmark seed: `{report.benchmark_seed}`",
        f"- Recommended candidate: `{report.recommended_candidate or 'none'}`",
        "- Production configuration modified: `false`",
        "",
        "| Candidate | Monotonic | Clean | Mild | Severe | Discrimination | Stable | Accepted |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for candidate in report.candidates:
        lines.append(
            f"| {candidate.candidate_name} | {candidate.monotonicity.passed} | "
            f"{candidate.clean_score:.2f} | {candidate.mild_score:.2f} | "
            f"{candidate.severe_score:.2f} | {candidate.discrimination:.2f} | "
            f"{candidate.stability_delta == 0.0} | {candidate.accepted} |"
        )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in report.limitations)
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "CandidateCalibration",
    "MonotonicityCheck",
    "MonotonicityReport",
    "ScoreCalibrationReport",
    "calibrate_score_profiles",
    "render_calibration_markdown",
    "validate_score_monotonicity",
]
