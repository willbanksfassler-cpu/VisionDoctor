"""Tests for reproducible corruption generation and location-aware metrics."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.generate_corruption_benchmark import generate_corruption_benchmark
from scripts.run_corruption_benchmark import run_benchmark
from vision_doctor.evaluation import (
    BenchmarkResult,
    DuplicateExpectation,
    IssueExpectation,
    evaluate_duplicate_groups,
    evaluate_issues,
    metrics_from_counts,
)
from vision_doctor.models import DuplicateGroup, Issue, Severity


def _issue(code: str, path: str, line: int | None = None) -> Issue:
    return Issue(
        issue_id=f"{code}-{path}-{line}",
        code=code,
        severity=Severity.WARNING,
        message="Synthetic test finding.",
        relative_path=path,
        annotation_line=line,
    )


def test_same_seed_reproduces_archives_and_ground_truth(tmp_path: Path) -> None:
    first = generate_corruption_benchmark(
        tmp_path / "first",
        profile="quick",
        seed=12345,
    )
    second = generate_corruption_benchmark(
        tmp_path / "second",
        profile="quick",
        seed=12345,
    )

    assert first.clean_archive.read_bytes() == second.clean_archive.read_bytes()
    assert (
        first.corrupted_archive.read_bytes()
        == second.corrupted_archive.read_bytes()
    )
    assert first.ground_truth_path.read_text(encoding="utf-8") == (
        second.ground_truth_path.read_text(encoding="utf-8")
    )
    assert first.ground_truth == second.ground_truth


def test_tp_fp_fn_micro_macro_and_unmatched_reasons_are_correct() -> None:
    expected = [
        IssueExpectation(
            code="CODE_A",
            relative_path="train/labels/a.txt",
            annotation_line=1,
        ),
        IssueExpectation(code="CODE_B", relative_path="train/images/b.jpg"),
    ]
    actual = [
        _issue("CODE_A", "train/labels/a.txt", 1),
        _issue("CODE_A", "train/labels/unexpected.txt", 2),
    ]

    summary = evaluate_issues(expected, actual)

    assert summary.per_code["CODE_A"].model_dump() == {
        "true_positive": 1,
        "false_positive": 1,
        "false_negative": 0,
        "precision": 0.5,
        "recall": 1.0,
        "f1": pytest.approx(2 / 3, abs=1e-6),
    }
    assert summary.per_code["CODE_B"].false_negative == 1
    assert summary.micro_average.model_dump() == {
        "precision": 0.5,
        "recall": 0.5,
        "f1": 0.5,
    }
    assert summary.macro_average.precision == pytest.approx(0.25)
    assert summary.macro_average.recall == pytest.approx(0.5)
    assert summary.macro_average.f1 == pytest.approx(1 / 3, abs=1e-6)
    assert len(summary.unmatched) == 2
    assert {item.side for item in summary.unmatched} == {"expected", "actual"}
    assert all(item.reason for item in summary.unmatched)


def test_zero_division_is_safe() -> None:
    missing = metrics_from_counts(0, 0, 1)
    unexpected = metrics_from_counts(0, 1, 0)
    empty = metrics_from_counts(0, 0, 0)

    assert (missing.precision, missing.recall, missing.f1) == (0.0, 0.0, 0.0)
    assert (unexpected.precision, unexpected.recall, unexpected.f1) == (
        0.0,
        0.0,
        0.0,
    )
    assert (empty.precision, empty.recall, empty.f1) == (0.0, 0.0, 0.0)


def test_paths_normalize_but_annotation_lines_must_match() -> None:
    expected = [
        IssueExpectation(
            code="LABEL_PARSE_ERROR",
            relative_path="train/labels/a.txt",
            annotation_line=3,
        )
    ]

    normalized = evaluate_issues(
        expected,
        [_issue("LABEL_PARSE_ERROR", r"train\labels\a.txt", 3)],
    )
    wrong_line = evaluate_issues(
        expected,
        [_issue("LABEL_PARSE_ERROR", "train/labels/a.txt", 4)],
    )

    assert normalized.micro_average.f1 == 1.0
    assert wrong_line.per_code["LABEL_PARSE_ERROR"].false_positive == 1
    assert wrong_line.per_code["LABEL_PARSE_ERROR"].false_negative == 1
    assert all("annotation line differs" in item.reason for item in wrong_line.unmatched)


def test_duplicate_groups_match_kind_and_complete_membership() -> None:
    expected = [
        DuplicateExpectation(kind="exact", image_ids=["b.jpg", "a.jpg"]),
        DuplicateExpectation(kind="near", image_ids=["a.jpg", "c.jpg"]),
    ]
    actual = [
        DuplicateGroup(
            group_id="exact",
            kind="exact",
            image_ids=["a.jpg", "b.jpg"],
        ),
        DuplicateGroup(
            group_id="near-wrong",
            kind="near",
            image_ids=["a.jpg", "d.jpg"],
        ),
    ]

    summary = evaluate_duplicate_groups(expected, actual)

    assert summary.per_code["DUPLICATE_EXACT"].f1 == 1.0
    assert summary.per_code["DUPLICATE_NEAR"].false_positive == 1
    assert summary.per_code["DUPLICATE_NEAR"].false_negative == 1
    assert any("group membership differs" in item.reason for item in summary.unmatched)


def test_quick_benchmark_runs_real_pipeline_and_writes_valid_json(
    tmp_path: Path,
) -> None:
    result, json_path, markdown_path = run_benchmark(
        tmp_path,
        profile="quick",
        seed=20261022,
    )
    restored = BenchmarkResult.model_validate_json(
        json_path.read_text(encoding="utf-8")
    )

    assert restored == result
    assert result.image_count == 40
    assert result.evaluation.distribution_matches_ground_truth is True
    assert result.evaluation.micro_average.f1 == 1.0
    assert result.evaluation.macro_average.f1 == 1.0
    assert result.evaluation.unmatched == []
    assert result.performance.total_seconds > 0
    assert result.performance.python_peak_memory_bytes > 0
    assert result.run_config["doctor_enabled"] is False
    assert {
        "LABEL_MISSING",
        "BBOX_TINY",
        "IMAGE_UNREADABLE",
        "DUPLICATE_EXACT",
        "DUPLICATE_NEAR",
        "CLASS_IMBALANCE",
    } <= set(result.evaluation.per_code)
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "synthetic controlled-corruption benchmark" in markdown
    assert "| LABEL_MISSING | 1 | 0 | 0 |" in markdown
