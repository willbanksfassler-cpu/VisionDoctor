"""Ground-truth matching and metrics for synthetic VisionDoctor benchmarks."""

from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from vision_doctor.models import AuditReport, DuplicateGroup, Issue

EXACT_DUPLICATE_SIGNAL = "DUPLICATE_EXACT"
NEAR_DUPLICATE_SIGNAL = "DUPLICATE_NEAR"
CLASS_IMBALANCE_SIGNAL = "CLASS_IMBALANCE"


class BenchmarkContract(BaseModel):
    """Strict base contract for reproducible benchmark artifacts."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class IssueExpectation(BenchmarkContract):
    """One injected issue identified by code and source location."""

    code: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    annotation_line: int | None = Field(default=None, ge=1)
    image_id: str | None = None


class DuplicateExpectation(BenchmarkContract):
    """One injected exact or near-duplicate group."""

    kind: Literal["exact", "near"]
    image_ids: list[str] = Field(min_length=2)

    @field_validator("image_ids")
    @classmethod
    def require_unique_members(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("duplicate expectation members must be unique")
        return sorted(value)


class DistributionExpectation(BenchmarkContract):
    """Known class-distribution facts created by the injector."""

    class_counts: dict[int, int]
    rare_class_ids: list[int]
    zero_instance_class_ids: list[int]
    min_imbalance_index: float = Field(gt=1.0)


class BenchmarkGroundTruth(BenchmarkContract):
    """Versioned truth file written beside every generated benchmark."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    profile: Literal["quick", "standard", "scale"]
    seed: int
    image_count: int = Field(ge=1)
    issues: list[IssueExpectation]
    duplicate_groups: list[DuplicateExpectation]
    distribution: DistributionExpectation
    notes: list[str] = Field(default_factory=list)


class CodeMetrics(BenchmarkContract):
    """Confusion counts and safe derived metrics for one finding code."""

    true_positive: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    false_negative: int = Field(ge=0)
    precision: float = Field(ge=0.0, le=1.0)
    recall: float = Field(ge=0.0, le=1.0)
    f1: float = Field(ge=0.0, le=1.0)


class AggregateMetrics(BenchmarkContract):
    """Micro or macro averages over all evaluated codes."""

    precision: float = Field(ge=0.0, le=1.0)
    recall: float = Field(ge=0.0, le=1.0)
    f1: float = Field(ge=0.0, le=1.0)


class UnmatchedFinding(BenchmarkContract):
    """A false negative or false positive with a diagnostic reason."""

    side: Literal["expected", "actual"]
    code: str
    relative_path: str
    annotation_line: int | None = None
    reason: str


class EvaluationSummary(BenchmarkContract):
    """Location-aware benchmark accuracy summary."""

    per_code: dict[str, CodeMetrics]
    micro_average: AggregateMetrics
    macro_average: AggregateMetrics
    unmatched: list[UnmatchedFinding]
    distribution_matches_ground_truth: bool


class PerformanceStats(BenchmarkContract):
    """Wall-clock and Python-allocation measurements for one pipeline run."""

    total_seconds: float = Field(ge=0.0)
    seconds_per_image: float = Field(ge=0.0)
    python_peak_memory_bytes: int = Field(ge=0)
    memory_caveat: str = (
        "tracemalloc measures Python-managed allocations and does not include all "
        "native-library memory used by NumPy, Pillow, or OpenCV."
    )


class QualityModeComparison(BenchmarkContract):
    """Observed accuracy and output counts for one threshold mode."""

    mode: Literal["fixed", "adaptive"]
    issue_counts: dict[str, int]
    micro_average: AggregateMetrics
    macro_average: AggregateMetrics
    unmatched_count: int = Field(ge=0)
    total_seconds: float = Field(ge=0.0)


class BenchmarkResult(BenchmarkContract):
    """Stable, machine-readable output from one benchmark execution."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    profile: Literal["quick", "standard", "scale"]
    seed: int
    image_count: int
    run_config: dict[str, JsonValue]
    evaluation: EvaluationSummary
    performance: PerformanceStats
    quality_mode_comparison: list[QualityModeComparison] = Field(
        default_factory=list
    )
    limitations: list[str]


FindingIdentity = tuple[str, str, int | None]


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def metrics_from_counts(tp: int, fp: int, fn: int) -> CodeMetrics:
    """Calculate precision, recall, and F1 without zero-division failures."""

    precision = _safe_ratio(tp, tp + fp)
    recall = _safe_ratio(tp, tp + fn)
    f1 = _safe_ratio(2.0 * precision * recall, precision + recall)
    return CodeMetrics(
        true_positive=tp,
        false_positive=fp,
        false_negative=fn,
        precision=round(precision, 6),
        recall=round(recall, 6),
        f1=round(f1, 6),
    )


def _normalize_path(value: str | None) -> str:
    normalized = (value or "<missing-path>").replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _issue_identity(issue: Issue | IssueExpectation) -> FindingIdentity:
    return (
        issue.code,
        _normalize_path(issue.relative_path),
        issue.annotation_line,
    )


def _duplicate_identity(
    group: DuplicateGroup | DuplicateExpectation,
) -> FindingIdentity:
    code = (
        EXACT_DUPLICATE_SIGNAL
        if group.kind == "exact"
        else NEAR_DUPLICATE_SIGNAL
    )
    members = "|".join(sorted(_normalize_path(item) for item in group.image_ids))
    return code, members, None


def _distribution_signature(
    class_counts: dict[int, int],
    rare_class_ids: list[int],
    zero_instance_class_ids: list[int],
) -> str:
    counts = ",".join(
        f"{class_id}:{count}" for class_id, count in sorted(class_counts.items())
    )
    rare = ",".join(str(item) for item in sorted(rare_class_ids))
    zero = ",".join(str(item) for item in sorted(zero_instance_class_ids))
    return f"counts={counts};rare={rare};zero={zero}"


def _expected_distribution_identity(
    expectation: DistributionExpectation,
) -> FindingIdentity:
    return (
        CLASS_IMBALANCE_SIGNAL,
        _distribution_signature(
            expectation.class_counts,
            expectation.rare_class_ids,
            expectation.zero_instance_class_ids,
        ),
        None,
    )


def _actual_distribution_identity(report: AuditReport) -> FindingIdentity | None:
    distribution = report.distribution
    has_imbalance = len(distribution.class_counts) > 1 and bool(
        distribution.zero_instance_class_ids
        or distribution.rare_class_ids
        or (distribution.imbalance_index or 1.0) > 1.0
    )
    if not has_imbalance:
        return None
    return (
        CLASS_IMBALANCE_SIGNAL,
        _distribution_signature(
            distribution.class_counts,
            distribution.rare_class_ids,
            distribution.zero_instance_class_ids,
        ),
        None,
    )


def _unmatched_reason(
    identity: FindingIdentity,
    candidates: list[FindingIdentity],
) -> str:
    code, path, line = identity
    same_code = [candidate for candidate in candidates if candidate[0] == code]
    if not same_code:
        return "No finding with this code exists on the other side."
    same_path = [candidate for candidate in same_code if candidate[1] == path]
    if not same_path:
        return "The code exists, but the relative path or group membership differs."
    if all(candidate[2] != line for candidate in same_path):
        return "The code and path match, but the annotation line differs."
    return "A matching identity exists but its duplicate occurrence count differs."


def _evaluate_identities(
    expected: list[FindingIdentity],
    actual: list[FindingIdentity],
    *,
    distribution_matches: bool,
) -> EvaluationSummary:
    expected_counts = Counter(expected)
    actual_counts = Counter(actual)
    codes = sorted({item[0] for item in expected + actual})
    per_code: dict[str, CodeMetrics] = {}
    unmatched: list[UnmatchedFinding] = []

    for code in codes:
        identities = sorted(
            {
                item
                for item in (*expected_counts.keys(), *actual_counts.keys())
                if item[0] == code
            },
            key=lambda item: (item[1], item[2] or 0),
        )
        tp = sum(
            min(expected_counts[item], actual_counts[item]) for item in identities
        )
        expected_total = sum(expected_counts[item] for item in identities)
        actual_total = sum(actual_counts[item] for item in identities)
        per_code[code] = metrics_from_counts(
            tp,
            actual_total - tp,
            expected_total - tp,
        )

    remaining_actual = actual_counts.copy()
    for identity in sorted(expected, key=lambda item: (item[0], item[1], item[2] or 0)):
        if remaining_actual[identity] > 0:
            remaining_actual[identity] -= 1
            continue
        unmatched.append(
            UnmatchedFinding(
                side="expected",
                code=identity[0],
                relative_path=identity[1],
                annotation_line=identity[2],
                reason=_unmatched_reason(identity, actual),
            )
        )

    remaining_expected = expected_counts.copy()
    for identity in sorted(actual, key=lambda item: (item[0], item[1], item[2] or 0)):
        if remaining_expected[identity] > 0:
            remaining_expected[identity] -= 1
            continue
        unmatched.append(
            UnmatchedFinding(
                side="actual",
                code=identity[0],
                relative_path=identity[1],
                annotation_line=identity[2],
                reason=_unmatched_reason(identity, expected),
            )
        )

    total_tp = sum(item.true_positive for item in per_code.values())
    total_fp = sum(item.false_positive for item in per_code.values())
    total_fn = sum(item.false_negative for item in per_code.values())
    micro_counts = metrics_from_counts(total_tp, total_fp, total_fn)
    micro = AggregateMetrics(
        precision=micro_counts.precision,
        recall=micro_counts.recall,
        f1=micro_counts.f1,
    )
    if per_code:
        count = len(per_code)
        macro = AggregateMetrics(
            precision=round(
                sum(item.precision for item in per_code.values()) / count, 6
            ),
            recall=round(
                sum(item.recall for item in per_code.values()) / count, 6
            ),
            f1=round(sum(item.f1 for item in per_code.values()) / count, 6),
        )
    else:
        macro = AggregateMetrics(precision=0.0, recall=0.0, f1=0.0)
    return EvaluationSummary(
        per_code=per_code,
        micro_average=micro,
        macro_average=macro,
        unmatched=unmatched,
        distribution_matches_ground_truth=distribution_matches,
    )


def evaluate_issues(
    expected: list[IssueExpectation],
    actual: list[Issue],
) -> EvaluationSummary:
    """Evaluate only product Issues; useful for focused unit tests."""

    return _evaluate_identities(
        [_issue_identity(item) for item in expected],
        [_issue_identity(item) for item in actual],
        distribution_matches=True,
    )


def evaluate_duplicate_groups(
    expected: list[DuplicateExpectation],
    actual: list[DuplicateGroup],
) -> EvaluationSummary:
    """Evaluate duplicate kind and complete group membership."""

    return _evaluate_identities(
        [_duplicate_identity(item) for item in expected],
        [_duplicate_identity(item) for item in actual],
        distribution_matches=True,
    )


def evaluate_benchmark_report(
    ground_truth: BenchmarkGroundTruth,
    report: AuditReport,
    *,
    total_seconds: float,
    python_peak_memory_bytes: int,
) -> BenchmarkResult:
    """Compare a complete pipeline report with injected, location-aware truth."""

    expected = [_issue_identity(item) for item in ground_truth.issues]
    expected.extend(
        _duplicate_identity(group) for group in ground_truth.duplicate_groups
    )
    expected_distribution = _expected_distribution_identity(
        ground_truth.distribution
    )
    expected.append(expected_distribution)

    actual = [_issue_identity(item) for item in report.issues]
    actual.extend(_duplicate_identity(group) for group in report.duplicate_groups)
    actual_distribution = _actual_distribution_identity(report)
    if actual_distribution is not None:
        actual.append(actual_distribution)

    distribution = ground_truth.distribution
    distribution_matches = bool(
        report.distribution.class_counts == distribution.class_counts
        and report.distribution.rare_class_ids == distribution.rare_class_ids
        and report.distribution.zero_instance_class_ids
        == distribution.zero_instance_class_ids
        and (report.distribution.imbalance_index or 1.0)
        >= distribution.min_imbalance_index
    )
    evaluation = _evaluate_identities(
        expected,
        actual,
        distribution_matches=distribution_matches,
    )
    seconds_per_image = _safe_ratio(total_seconds, ground_truth.image_count)
    return BenchmarkResult(
        profile=ground_truth.profile,
        seed=ground_truth.seed,
        image_count=ground_truth.image_count,
        run_config={
            "doctor_enabled": False,
            "source_archive": report.manifest.source_archive,
            "threshold_snapshot": report.threshold_snapshot,
        },
        evaluation=evaluation,
        performance=PerformanceStats(
            total_seconds=round(total_seconds, 6),
            seconds_per_image=round(seconds_per_image, 6),
            python_peak_memory_bytes=python_peak_memory_bytes,
        ),
        limitations=[
            (
                "This is a synthetic controlled-corruption benchmark, not validation "
                "on real business data."
            ),
            (
                "Metrics measure the current injected scenarios and do not prove "
                "coverage of all possible dataset failures."
            ),
            (
                "Peak memory is based on tracemalloc and excludes some native-library "
                "allocations."
            ),
        ],
    )


def render_benchmark_markdown(result: BenchmarkResult) -> str:
    """Render a stable, compact Markdown summary from a benchmark result."""

    lines = [
        "# VisionDoctor controlled-corruption benchmark",
        "",
        f"- Profile: `{result.profile}`",
        f"- Seed: `{result.seed}`",
        f"- Images: `{result.image_count}`",
        f"- Total pipeline time: `{result.performance.total_seconds:.6f}s`",
        (
            "- Mean time per image: "
            f"`{result.performance.seconds_per_image:.6f}s`"
        ),
        (
            "- Python peak memory: "
            f"`{result.performance.python_peak_memory_bytes}` bytes"
        ),
        "- Dataset Doctor / external API: `disabled`",
        "",
        "## Accuracy",
        "",
        "| Code | TP | FP | FN | Precision | Recall | F1 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for code, metric in result.evaluation.per_code.items():
        lines.append(
            f"| {code} | {metric.true_positive} | {metric.false_positive} | "
            f"{metric.false_negative} | {metric.precision:.6f} | "
            f"{metric.recall:.6f} | {metric.f1:.6f} |"
        )
    lines.extend(
        [
            "",
            (
                "- Micro average: "
                f"P={result.evaluation.micro_average.precision:.6f}, "
                f"R={result.evaluation.micro_average.recall:.6f}, "
                f"F1={result.evaluation.micro_average.f1:.6f}"
            ),
            (
                "- Macro average: "
                f"P={result.evaluation.macro_average.precision:.6f}, "
                f"R={result.evaluation.macro_average.recall:.6f}, "
                f"F1={result.evaluation.macro_average.f1:.6f}"
            ),
            (
                "- Distribution matches injected truth: "
                f"`{str(result.evaluation.distribution_matches_ground_truth).lower()}`"
            ),
            "",
            "## Unmatched findings",
            "",
        ]
    )
    if result.evaluation.unmatched:
        for finding in result.evaluation.unmatched:
            location = finding.relative_path
            if finding.annotation_line is not None:
                location = f"{location}:{finding.annotation_line}"
            lines.append(
                f"- `{finding.side}` `{finding.code}` at `{location}`: "
                f"{finding.reason}"
            )
    else:
        lines.append("- None.")
    if result.quality_mode_comparison:
        lines.extend(["", "## Fixed vs adaptive", ""])
        for comparison in result.quality_mode_comparison:
            lines.append(
                f"- `{comparison.mode}`: micro F1 "
                f"`{comparison.micro_average.f1:.6f}`, macro F1 "
                f"`{comparison.macro_average.f1:.6f}`, unmatched "
                f"`{comparison.unmatched_count}`, runtime "
                f"`{comparison.total_seconds:.6f}s`."
            )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in result.limitations)
    lines.extend(["", f"> {result.performance.memory_caveat}", ""])
    return "\n".join(lines)
