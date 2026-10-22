"""Deterministic Dataset Doctor diagnosis when LLM use is unavailable."""

from __future__ import annotations

from collections import defaultdict

from vision_doctor.models import (
    AuditReport,
    Diagnosis,
    EvidenceClaim,
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


def _action_for(code: str, report: AuditReport) -> str:
    knowledge = report.knowledge_guidance
    if knowledge is not None:
        entry = next(
            (
                item
                for item in knowledge.guidance_entries
                if code in item.applicable_issue_codes
            ),
            None,
        )
        if entry is not None:
            return (
                f"场景指导（{knowledge.profile_id.value}，知识包 "
                f"{knowledge.pack_schema_version}；仅供参考）：{entry.guidance}"
            )
    if code.startswith("LABEL_") or code == "CLASS_ID_INVALID":
        return "对照原图复核相关标签，只有在人工确认后再进行修改。"
    if code.startswith("BBOX_"):
        return "对照原图检查边界框，确认后再修改标签。"
    if code.startswith("IMAGE_"):
        return "检查源图片质量，再决定是否替换或重新导出。"
    return "复核检测证据，并判断处理方式是否符合数据集的真实用途。"


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
                    f"检测到 {len(members)} 个 {code} 问题，"
                    f"影响 {affected} 个不同对象。"
                ),
                severity=severity,
                issue_ids=issue_ids,
                affected_count=affected,
                score_penalty=penalty,
                inference=(
                    "这可能影响数据集可用性，但目前没有真实模型效果测量证据。"
                ),
                needs_human_confirmation=True,
            )
        )
        actions.append(
            RecommendedAction(
                action_id=f"fallback-action-{rank}-{code.lower()}",
                priority=rank,
                title=f"复核 {code}",
                description=_action_for(code, report),
                related_issue_ids=issue_ids,
                estimated_effort="medium",
            )
        )

    level = _risk_level(report)
    level_label = {
        "low": "低",
        "medium": "中",
        "high": "高",
        "critical": "严重",
    }[level]
    knowledge_caveats: list[str] = []
    if report.knowledge_guidance is not None:
        knowledge = report.knowledge_guidance
        knowledge_caveats = [
            knowledge.advisory_notice,
            (
                f"当前场景知识包：{knowledge.profile_id.value}；"
                f"版本：{knowledge.pack_schema_version}。"
            ),
            *[
                f"人工复核问题：{question}"
                for question in knowledge.recommended_questions[:2]
            ],
            *knowledge.caveats[:2],
        ]
    return Diagnosis(
        generated_by="deterministic",
        risk_level=level,
        summary=(
            f"数据集健康分为 {report.health_score.overall:.2f}/100（等级 "
            f"{report.health_score.grade}），确定性风险级别为{level_label}。"
        ),
        priority_findings=findings,
        recommended_actions=actions,
        evidence_claims=[
            EvidenceClaim(
                claim_type="health_score",
                metric_name="overall",
                claimed_value=report.health_score.overall,
                source_tool="get_score_component",
                classification="fact",
            ),
            EvidenceClaim(
                claim_type="dataset_count",
                metric_name="issue_count",
                claimed_value=len(report.issues),
                source_tool="get_dataset_summary",
                classification="fact",
            ),
        ],
        caveats=[
            "本诊断只使用确定性规则和已观察到的体检证据。",
            "任何修复都不保证提升 mAP 或其他模型指标。",
            "空标签可能是合法负样本，需要人工确认。",
            "类别不平衡可能符合真实业务分布。",
            "系统没有修改任何源图片或标签。",
            *knowledge_caveats,
        ],
    )
