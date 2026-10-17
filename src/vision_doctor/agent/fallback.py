"""Deterministic Dataset Doctor diagnosis when LLM use is unavailable."""

from __future__ import annotations

from collections import defaultdict

from vision_doctor.models import (
    AuditReport,
    Diagnosis,
    Issue,
    PriorityFinding,
    RecommendedAction,
    Severity,
)
from vision_doctor.scoring import BBOX_CODES, IMAGE_CODES, STRUCTURAL_CODES

_SEVERITY_RANK = {
    Severity.INFO: 0,
    Severity.WARNING: 1,
    Severity.ERROR: 2,
    Severity.CRITICAL: 3,
}


def _score_category(code: str) -> str | None:
    if code in STRUCTURAL_CODES:
        return "structural"
    if code in BBOX_CODES:
        return "bbox"
    if code in IMAGE_CODES:
        return "image"
    return None


def _risk_level(report: AuditReport) -> str:
    severities = {issue.severity for issue in report.issues}
    if Severity.CRITICAL in severities or report.health_score.overall < 40:
        return "critical"
    if Severity.ERROR in severities or report.health_score.overall < 60:
        return "high"
    if Severity.WARNING in severities or report.health_score.overall < 80:
        return "medium"
    return "low"


def _action_for(code: str) -> str:
    if code.startswith("LABEL_") or code == "CLASS_ID_INVALID":
        return "Review the referenced labels and correct only after human confirmation."
    if code.startswith("BBOX_"):
        return "Review bounding boxes against source images before correcting labels."
    if code.startswith("IMAGE_"):
        return "Inspect source image quality and replace or re-export when appropriate."
    return "Review the evidence and decide whether remediation matches dataset intent."


def build_fallback_diagnosis(report: AuditReport) -> Diagnosis:
    """Prioritize observed groups by severity, affected count, then score penalty."""

    grouped: dict[str, list[Issue]] = defaultdict(list)
    for issue in report.issues:
        grouped[issue.code].append(issue)
    ranked: list[tuple[int, int, float, str, Severity, list[Issue]]] = []
    for code, members in grouped.items():
        severity = max(members, key=lambda item: _SEVERITY_RANK[item.severity]).severity
        affected = len(
            {item.image_id or item.relative_path or item.issue_id for item in members}
        )
        category = _score_category(code)
        penalty = report.health_score.penalties.get(category, 0.0) if category else 0.0
        ranked.append(
            (_SEVERITY_RANK[severity], affected, penalty, code, severity, members)
        )
    ranked.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))

    findings: list[PriorityFinding] = []
    actions: list[RecommendedAction] = []
    for rank, (_, affected, penalty, code, severity, members) in enumerate(
        ranked[:5], start=1
    ):
        issue_ids = [item.issue_id for item in members]
        findings.append(
            PriorityFinding(
                rank=rank,
                title=code,
                rationale=(
                    f"Observed {len(members)} {code} issue(s) affecting "
                    f"{affected} distinct item(s)."
                ),
                severity=severity,
                issue_ids=issue_ids,
                affected_count=affected,
                score_penalty=penalty,
                inference=(
                    "This may reduce dataset usability, but impact on model performance "
                    "has not been measured."
                ),
                needs_human_confirmation=True,
            )
        )
        actions.append(
            RecommendedAction(
                action_id=f"fallback-action-{rank}-{code.lower()}",
                priority=rank,
                title=f"Review {code}",
                description=_action_for(code),
                related_issue_ids=issue_ids,
                estimated_effort="medium",
            )
        )

    level = _risk_level(report)
    return Diagnosis(
        generated_by="deterministic",
        risk_level=level,
        summary=(
            f"Dataset health score is {report.health_score.overall:.2f}/100 "
            f"(grade {report.health_score.grade}); deterministic risk level is {level}."
        ),
        priority_findings=findings,
        recommended_actions=actions,
        caveats=[
            "This diagnosis uses deterministic heuristics and observed audit evidence only.",
            "No repair is guaranteed to improve mAP or any other model metric.",
            "Empty labels may be valid negative samples and require human confirmation.",
            "Class imbalance may reflect the intended business distribution.",
            "No source image or label was modified.",
        ],
    )
