"""Deterministic retrieval over validated scenario guidance."""

from __future__ import annotations

from vision_doctor.knowledge.loader import (
    load_knowledge_pack,
    resolve_knowledge_profile,
)
from vision_doctor.models import (
    AuditReport,
    KnowledgeGuidanceContext,
    KnowledgeGuidanceEntry,
    KnowledgeProfile,
)


def _active_signals(report: AuditReport) -> set[str]:
    issue_codes = {issue.code for issue in report.issues}
    signals = {"always"}
    if (
        report.distribution.rare_class_ids
        or report.distribution.zero_instance_class_ids
        or (report.distribution.imbalance_index or 1.0) > 1.0
    ):
        signals.add("class_distribution")
    if any(code.startswith("BBOX_") for code in issue_codes):
        signals.add("bbox_statistics")
    if any(code.startswith("IMAGE_") for code in issue_codes):
        signals.add("image_quality")
    if any(code.startswith("SPLIT_LEAKAGE_") for code in issue_codes):
        signals.add("split_leakage")
    if report.repair_simulation and report.repair_simulation.impacts:
        signals.add("repair_simulation")
    return signals


def _entry_score(
    entry: KnowledgeGuidanceEntry,
    *,
    issue_codes: set[str],
    signals: set[str],
) -> int:
    issue_matches = len(set(entry.applicable_issue_codes) & issue_codes)
    signal_matches = len(set(entry.evidence_signals) & signals)
    return issue_matches * 100 + signal_matches * 10


def retrieve_knowledge(
    report: AuditReport,
    profile: KnowledgeProfile | str = KnowledgeProfile.GENERIC,
    *,
    max_guidance_items: int = 5,
    max_questions: int = 5,
) -> KnowledgeGuidanceContext:
    """Select bounded advice from report aggregates, never dataset text."""

    if not 1 <= max_guidance_items <= 10:
        raise ValueError("max_guidance_items must be in [1, 10]")
    if not 1 <= max_questions <= 10:
        raise ValueError("max_questions must be in [1, 10]")
    selected, fallback_reason = resolve_knowledge_profile(profile)
    pack = load_knowledge_pack(selected, fallback_to_generic=False)
    issue_codes = {issue.code for issue in report.issues}
    signals = _active_signals(report)
    scored = [
        (_entry_score(entry, issue_codes=issue_codes, signals=signals), entry)
        for entry in pack.review_guidance
    ]
    entries = [
        entry
        for score, entry in sorted(
            scored,
            key=lambda item: (-item[0], item[1].guidance_id),
        )
        if score > 0
    ][:max_guidance_items]
    return KnowledgeGuidanceContext(
        profile_id=selected,
        display_name=pack.display_name,
        pack_schema_version=pack.schema_version,
        used_guidance_entry_ids=[entry.guidance_id for entry in entries],
        guidance_entries=entries,
        recommended_questions=pack.recommended_questions[:max_questions],
        caveats=pack.caveats[:max_questions],
        source=pack.source,
        provenance=pack.provenance,
        fallback_reason=fallback_reason,
    )
