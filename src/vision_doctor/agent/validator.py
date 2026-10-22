"""Deterministic fact checks for structured Dataset Doctor output."""

from __future__ import annotations

import math
import re
from enum import Enum

from pydantic import BaseModel, ConfigDict

from vision_doctor.models import AuditReport, Diagnosis, EvidenceClaim, Severity

_SEVERITY_RANK = {
    Severity.INFO: 0,
    Severity.WARNING: 1,
    Severity.ERROR: 2,
    Severity.CRITICAL: 3,
}


class FactValidationCode(str, Enum):
    """Sanitized validation failures, ordered later by client policy."""

    GENERATED_BY_MISMATCH = "generated_by_mismatch"
    UNKNOWN_ISSUE_REFERENCE = "unknown_issue_reference"
    CLAIM_SOURCE_MISMATCH = "claim_source_mismatch"
    CLAIM_VALUE_MISMATCH = "claim_value_mismatch"
    SEVERITY_MISMATCH = "severity_mismatch"
    CRITICAL_ISSUE_OMITTED = "critical_issue_omitted"
    PROHIBITED_PERFORMANCE_PROMISE = "prohibited_performance_promise"
    DATA_MODIFICATION_CLAIM = "data_modification_claim"


class FactValidationResult(BaseModel):
    """No provider text is retained; only sanitized codes are returned."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    valid: bool
    failures: list[FactValidationCode]


_EXPECTED_SOURCES: dict[str, set[str]] = {
    "dataset_count": {"get_dataset_summary"},
    "issue_count": {"get_issue_group", "get_representative_issues"},
    "health_score": {"get_dataset_summary", "get_score_component"},
    "score_penalty": {"get_score_component"},
    "class_instance_count": {"get_class_distribution"},
    "duplicate_group_count": {"get_duplicate_summary"},
    "split_leakage_group_count": {"get_split_leakage_summary"},
    "repair_simulation": {"get_repair_simulations"},
    "qualitative": {
        "get_dataset_summary",
        "get_issue_group",
        "get_representative_issues",
        "get_class_distribution",
        "get_score_component",
        "get_duplicate_summary",
        "get_split_leakage_summary",
        "get_repair_simulations",
    },
}


def _equal_value(claimed: object, actual: object) -> bool:
    if isinstance(claimed, bool) or isinstance(actual, bool):
        return claimed is actual
    if isinstance(claimed, int | float) and isinstance(actual, int | float):
        return math.isclose(float(claimed), float(actual), abs_tol=1e-6)
    return claimed == actual


def _duplicate_count(report: AuditReport, metric_name: str) -> int | None:
    if metric_name == "all":
        return len(report.duplicate_groups)
    if metric_name in {"exact", "near"}:
        return sum(group.kind == metric_name for group in report.duplicate_groups)
    return None


def _leakage_count(report: AuditReport, metric_name: str) -> int | None:
    code_by_kind = {
        "exact": "SPLIT_LEAKAGE_EXACT",
        "near": "SPLIT_LEAKAGE_NEAR",
    }
    if metric_name not in {"all", "exact", "near"}:
        return None
    issues = [
        issue
        for issue in report.issues
        if issue.code in set(code_by_kind.values())
        and (metric_name == "all" or issue.code == code_by_kind[metric_name])
    ]
    group_ids = {
        issue.evidence.get("duplicate_group_id")
        for issue in issues
        if isinstance(issue.evidence.get("duplicate_group_id"), str)
    }
    return len(group_ids)


def _repair_delta(report: AuditReport, metric_name: str) -> float | None:
    if report.repair_simulation is None:
        return None
    for impact in report.repair_simulation.impacts:
        if impact.scenario.scenario_id == metric_name:
            return impact.score_delta
    return None


def _actual_claim_value(report: AuditReport, claim: EvidenceClaim) -> object | None:
    if claim.claim_type == "dataset_count":
        values = report.manifest.summary.model_dump(mode="json")
        return values.get(claim.metric_name)
    if claim.claim_type == "issue_count":
        return sum(issue.code == claim.metric_name for issue in report.issues)
    if claim.claim_type == "health_score":
        if claim.metric_name == "overall":
            return report.health_score.overall
        if claim.metric_name == "grade":
            return report.health_score.grade
        return None
    if claim.claim_type == "score_penalty":
        return report.health_score.penalties.get(claim.metric_name)
    if claim.claim_type == "class_instance_count":
        try:
            class_id = int(claim.metric_name)
        except ValueError:
            return None
        return report.distribution.class_counts.get(class_id)
    if claim.claim_type == "duplicate_group_count":
        return _duplicate_count(report, claim.metric_name)
    if claim.claim_type == "split_leakage_group_count":
        return _leakage_count(report, claim.metric_name)
    if claim.claim_type == "repair_simulation":
        return _repair_delta(report, claim.metric_name)
    return claim.claimed_value


def _diagnosis_text(diagnosis: Diagnosis) -> list[str]:
    values = [diagnosis.summary, *diagnosis.caveats]
    for finding in diagnosis.priority_findings:
        values.extend(
            [
                finding.title,
                finding.rationale,
                finding.inference or "",
            ]
        )
    for action in diagnosis.recommended_actions:
        values.extend([action.title, action.description])
    values.extend(
        str(claim.claimed_value)
        for claim in diagnosis.evidence_claims
        if claim.claim_type == "qualitative"
    )
    return values


def _has_prohibited_map_promise(texts: list[str]) -> bool:
    for text in texts:
        normalized = " ".join(text.casefold().split())
        if "map" not in normalized and "模型性能" not in normalized:
            continue
        negative = bool(
            re.search(
                r"\b(?:no|not|never|cannot|can't|doesn't|isn't)\b.{0,50}"
                r"(?:guarantee|ensure|promise|improve|increase)",
                normalized,
            )
        ) or any(marker in normalized for marker in ("不保证", "无法保证", "不能保证"))
        if negative:
            continue
        positive = bool(
            re.search(
                r"\b(?:guarantee|ensure|promise|will|definitely|certainly)\b"
                r".{0,60}\b(?:improve|increase|raise|boost)\b",
                normalized,
            )
        ) or bool(re.search(r"(?:保证|必然|一定).{0,20}(?:提升|提高).{0,10}m?ap", normalized))
        if positive:
            return True
    return False


def _claims_data_was_modified(texts: list[str]) -> bool:
    patterns = (
        (
            r"\b(?:we|visiondoctor|dataset doctor|the system|the tool)\b.{0,30}"
            r"\b(?:modified|fixed|repaired|changed|deleted|removed)\b"
        ),
        (
            r"\b(?:the )?(?:dataset|data|labels?|images?)\b.{0,15}"
            r"\b(?:has|have) been "
            r"(?:modified|fixed|repaired|changed|deleted|removed)\b"
        ),
        r"(?:已|已经)(?:修改|修复|删除|移除).{0,10}(?:数据|标签|图片|文件)",
    )
    return any(
        re.search(pattern, text.casefold())
        for text in texts
        for pattern in patterns
    )


def validate_diagnosis_facts(
    diagnosis: Diagnosis,
    report: AuditReport,
) -> FactValidationResult:
    """Validate structured facts and safety claims against immutable report data."""

    failures: set[FactValidationCode] = set()
    if diagnosis.generated_by != "llm":
        failures.add(FactValidationCode.GENERATED_BY_MISMATCH)

    known_issues = {issue.issue_id: issue for issue in report.issues}
    referenced = {
        issue_id
        for finding in diagnosis.priority_findings
        for issue_id in finding.issue_ids
    }
    referenced.update(
        issue_id
        for action in diagnosis.recommended_actions
        for issue_id in action.related_issue_ids
    )
    referenced.update(
        issue_id
        for claim in diagnosis.evidence_claims
        for issue_id in claim.related_issue_ids
    )
    if not referenced <= set(known_issues):
        failures.add(FactValidationCode.UNKNOWN_ISSUE_REFERENCE)

    for claim in diagnosis.evidence_claims:
        if claim.source_tool not in _EXPECTED_SOURCES[claim.claim_type]:
            failures.add(FactValidationCode.CLAIM_SOURCE_MISMATCH)
        if claim.classification != "fact" or claim.claim_type == "qualitative":
            continue
        actual = _actual_claim_value(report, claim)
        if actual is None or not _equal_value(claim.claimed_value, actual):
            failures.add(FactValidationCode.CLAIM_VALUE_MISMATCH)

    for finding in diagnosis.priority_findings:
        evidence = [
            known_issues[issue_id]
            for issue_id in finding.issue_ids
            if issue_id in known_issues
        ]
        if not evidence:
            continue
        expected = max(
            evidence,
            key=lambda issue: _SEVERITY_RANK[issue.severity],
        ).severity
        if finding.severity != expected:
            failures.add(FactValidationCode.SEVERITY_MISMATCH)

    critical_ids = {
        issue.issue_id
        for issue in report.issues
        if issue.severity is Severity.CRITICAL
    }
    finding_ids = {
        issue_id
        for finding in diagnosis.priority_findings
        for issue_id in finding.issue_ids
    }
    if not critical_ids <= finding_ids:
        failures.add(FactValidationCode.CRITICAL_ISSUE_OMITTED)

    texts = _diagnosis_text(diagnosis)
    if _has_prohibited_map_promise(texts):
        failures.add(FactValidationCode.PROHIBITED_PERFORMANCE_PROMISE)
    if _claims_data_was_modified(texts):
        failures.add(FactValidationCode.DATA_MODIFICATION_CLAIM)

    ordered = sorted(failures, key=lambda item: item.value)
    return FactValidationResult(valid=not ordered, failures=ordered)


__all__ = [
    "FactValidationCode",
    "FactValidationResult",
    "validate_diagnosis_facts",
]
