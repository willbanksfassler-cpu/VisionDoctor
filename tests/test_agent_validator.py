"""Tests for deterministic validation of structured LLM claims."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.generate_demo_dataset import generate_demo_zip
from vision_doctor.agent.validator import (
    FactValidationCode,
    validate_diagnosis_facts,
)
from vision_doctor.models import (
    Diagnosis,
    EvidenceClaim,
    PriorityFinding,
    Severity,
)
from vision_doctor.pipeline import run_pipeline


def _report(tmp_path: Path):
    return run_pipeline(
        generate_demo_zip(tmp_path / "demo.zip"),
        temp_root=tmp_path,
    )


def _diagnosis(report, *, claims: list[EvidenceClaim] | None = None) -> Diagnosis:
    issue = report.issues[0]
    return Diagnosis(
        generated_by="llm",
        risk_level="medium",
        summary="Evidence-backed review requiring human confirmation.",
        priority_findings=[
            PriorityFinding(
                rank=1,
                title=issue.code,
                rationale="The cited issue was returned by a read-only tool.",
                severity=issue.severity,
                issue_ids=[issue.issue_id],
            )
        ],
        evidence_claims=claims or [],
        caveats=["No improvement in mAP is guaranteed."],
    )


def _claim(
    claim_type: str,
    metric_name: str,
    value: object,
    source: str,
) -> EvidenceClaim:
    return EvidenceClaim(
        claim_type=claim_type,
        metric_name=metric_name,
        claimed_value=value,
        source_tool=source,
        classification="fact",
    )


def test_valid_counts_scores_classes_duplicates_and_leakage_pass(
    tmp_path: Path,
) -> None:
    report = _report(tmp_path)
    claims = [
        _claim(
            "dataset_count",
            "image_count",
            report.manifest.summary.image_count,
            "get_dataset_summary",
        ),
        _claim(
            "issue_count",
            "IMAGE_BLURRY",
            sum(issue.code == "IMAGE_BLURRY" for issue in report.issues),
            "get_issue_group",
        ),
        _claim(
            "health_score",
            "overall",
            report.health_score.overall,
            "get_score_component",
        ),
        _claim(
            "score_penalty",
            "image",
            report.health_score.penalties["image"],
            "get_score_component",
        ),
        _claim(
            "class_instance_count",
            "0",
            report.distribution.class_counts[0],
            "get_class_distribution",
        ),
        _claim(
            "duplicate_group_count",
            "all",
            len(report.duplicate_groups),
            "get_duplicate_summary",
        ),
        _claim(
            "split_leakage_group_count",
            "near",
            1,
            "get_split_leakage_summary",
        ),
    ]

    result = validate_diagnosis_facts(_diagnosis(report, claims=claims), report)

    assert result.valid is True
    assert result.failures == []


@pytest.mark.parametrize(
    ("claim", "expected"),
    [
        (
            ("dataset_count", "image_count", 999, "get_dataset_summary"),
            FactValidationCode.CLAIM_VALUE_MISMATCH,
        ),
        (
            ("health_score", "overall", 99.9, "get_score_component"),
            FactValidationCode.CLAIM_VALUE_MISMATCH,
        ),
        (
            ("score_penalty", "image", 99.9, "get_score_component"),
            FactValidationCode.CLAIM_VALUE_MISMATCH,
        ),
        (
            ("class_instance_count", "0", 999, "get_class_distribution"),
            FactValidationCode.CLAIM_VALUE_MISMATCH,
        ),
        (
            ("duplicate_group_count", "all", 999, "get_duplicate_summary"),
            FactValidationCode.CLAIM_VALUE_MISMATCH,
        ),
        (
            (
                "split_leakage_group_count",
                "near",
                999,
                "get_split_leakage_summary",
            ),
            FactValidationCode.CLAIM_VALUE_MISMATCH,
        ),
        (
            ("health_score", "overall", 61.93, "get_class_distribution"),
            FactValidationCode.CLAIM_SOURCE_MISMATCH,
        ),
    ],
)
def test_incorrect_or_wrongly_sourced_claims_fail(
    tmp_path: Path,
    claim: tuple[str, str, object, str],
    expected: FactValidationCode,
) -> None:
    report = _report(tmp_path)
    diagnosis = _diagnosis(report, claims=[_claim(*claim)])

    assert expected in validate_diagnosis_facts(diagnosis, report).failures


def test_unknown_issue_and_incompatible_severity_fail(tmp_path: Path) -> None:
    report = _report(tmp_path)
    issue = report.issues[0]
    wrong_severity = Severity.INFO if issue.severity is not Severity.INFO else Severity.ERROR
    diagnosis = _diagnosis(report).model_copy(
        update={
            "priority_findings": [
                PriorityFinding(
                    rank=1,
                    title="Mismatch",
                    rationale="Mismatch",
                    severity=wrong_severity,
                    issue_ids=[issue.issue_id, "unknown-issue"],
                )
            ]
        }
    )

    failures = validate_diagnosis_facts(diagnosis, report).failures

    assert FactValidationCode.UNKNOWN_ISSUE_REFERENCE in failures
    assert FactValidationCode.SEVERITY_MISMATCH in failures


def test_critical_issues_must_appear_in_priority_findings(tmp_path: Path) -> None:
    report = _report(tmp_path)
    critical = report.issues[0].model_copy(update={"severity": Severity.CRITICAL})
    critical_report = report.model_copy(
        update={"issues": [critical, *report.issues[1:]]}
    )
    diagnosis = Diagnosis(
        generated_by="llm",
        risk_level="critical",
        summary="Critical evidence exists.",
    )

    result = validate_diagnosis_facts(diagnosis, critical_report)

    assert FactValidationCode.CRITICAL_ISSUE_OMITTED in result.failures


def test_prohibited_map_promise_and_modified_data_claim_fail(tmp_path: Path) -> None:
    report = _report(tmp_path)
    diagnosis = _diagnosis(report).model_copy(
        update={
            "summary": (
                "We already modified the labels and guarantee this will improve mAP."
            )
        }
    )

    failures = validate_diagnosis_facts(diagnosis, report).failures

    assert FactValidationCode.PROHIBITED_PERFORMANCE_PROMISE in failures
    assert FactValidationCode.DATA_MODIFICATION_CLAIM in failures


def test_generated_by_must_be_llm_for_llm_validation(tmp_path: Path) -> None:
    report = _report(tmp_path)
    diagnosis = _diagnosis(report).model_copy(
        update={"generated_by": "deterministic"}
    )

    assert FactValidationCode.GENERATED_BY_MISMATCH in (
        validate_diagnosis_facts(diagnosis, report).failures
    )
