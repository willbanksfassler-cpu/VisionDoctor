"""Tests for gated score calibration and deterministic invariants."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.calibrate_health_score import run_calibration
from vision_doctor.config import ScoringConfig
from vision_doctor.evaluation import (
    AggregateMetrics,
    BenchmarkResult,
    EvaluationSummary,
    PerformanceStats,
)
from vision_doctor.scoring import LEGACY_V1_PROFILE
from vision_doctor.scoring_calibration import (
    calibrate_score_profiles,
    validate_score_monotonicity,
)


def _benchmark(profile: str = "quick") -> BenchmarkResult:
    perfect = AggregateMetrics(precision=1.0, recall=1.0, f1=1.0)
    return BenchmarkResult(
        profile=profile,
        seed=42,
        image_count=40,
        run_config={},
        evaluation=EvaluationSummary(
            per_code={},
            micro_average=perfect,
            macro_average=perfect,
            unmatched=[],
            distribution_matches_ground_truth=True,
        ),
        performance=PerformanceStats(
            total_seconds=1.0,
            seconds_per_image=0.025,
            python_peak_memory_bytes=100,
        ),
        limitations=["synthetic"],
    )


def test_legacy_profile_passes_all_deterministic_monotonicity_checks() -> None:
    report = validate_score_monotonicity(LEGACY_V1_PROFILE)

    assert report.passed is True
    assert len(report.checks) == 10
    assert all(check.passed for check in report.checks)
    assert {check.name for check in report.checks} >= {
        "category_cap_stability",
        "empty_label_no_penalty",
        "single_class_distribution_zero",
        "deterministic_repeatability",
    }


def test_quick_synthetic_benchmark_does_not_recommend_calibrated_v2() -> None:
    report = calibrate_score_profiles(_benchmark())

    assert report.recommended_candidate is None
    assert report.production_configuration_modified is False
    assert len(report.candidates) == 3
    assert all(candidate.monotonicity.passed for candidate in report.candidates)
    assert all(not candidate.accepted for candidate in report.candidates)
    assert all(
        candidate.acceptance_conditions["standard_or_scale_profile"] is False
        for candidate in report.candidates
    )


def test_calibrated_v2_requires_explicit_accepted_standard_or_scale_evidence() -> None:
    with pytest.raises(ValidationError, match="standard/scale benchmark"):
        ScoringConfig(
            profile_name="calibrated-v2",
            calibrated_v2_enabled=True,
            calibration_metadata={
                "acceptance_passed": True,
                "benchmark_profile": "quick",
                "benchmark_schema_version": "1.0.0",
                "monotonicity_passed": True,
            },
        )

    accepted = ScoringConfig(
        profile_name="calibrated-v2",
        calibrated_v2_enabled=True,
        calibration_metadata={
            "acceptance_passed": True,
            "benchmark_profile": "standard",
            "benchmark_schema_version": "1.0.0",
            "monotonicity_passed": True,
        },
    )
    assert accepted.profile_name == "calibrated-v2"


def test_calibration_script_reads_benchmark_and_writes_parseable_outputs(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "quick"
    directory.mkdir()
    (directory / "result.json").write_text(
        _benchmark().model_dump_json(indent=2),
        encoding="utf-8",
    )

    report, json_path, markdown_path = run_calibration(tmp_path, profile="quick")

    assert json.loads(json_path.read_text(encoding="utf-8"))["schema_version"] == (
        "1.0.0"
    )
    assert "synthetic" in markdown_path.read_text(encoding="utf-8").lower()
    assert report.recommended_candidate is None
    assert report.production_configuration_modified is False
