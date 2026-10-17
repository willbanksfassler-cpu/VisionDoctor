"""Dataset Doctor diagnosis presentation."""

from __future__ import annotations

import streamlit as st

from vision_doctor.models import AuditReport


def render_doctor_panel(report: AuditReport) -> None:
    """Render assessment, risk, findings, actions, and caveats."""

    st.subheader("AI Doctor")
    diagnosis = report.diagnosis
    if diagnosis is None:
        st.info("Dataset Doctor was not run for this report.")
        return
    mode = "LLM" if diagnosis.generated_by == "llm" else "Deterministic fallback"
    first, second = st.columns(2)
    first.metric("Mode", mode)
    second.metric("Risk", diagnosis.risk_level.title())
    st.markdown("#### Assessment")
    st.write(diagnosis.summary)
    st.markdown("#### Priority findings")
    if not diagnosis.priority_findings:
        st.info("No priority finding was produced.")
    for finding in sorted(diagnosis.priority_findings, key=lambda item: item.rank):
        with st.expander(f"{finding.rank}. {finding.title}"):
            st.write(finding.rationale)
            if finding.inference:
                st.caption(f"Inference: {finding.inference}")
            st.caption(
                f"Severity: {finding.severity.value}; affected: {finding.affected_count}; "
                f"score penalty: {finding.score_penalty:.2f}"
            )
    st.markdown("#### Action plan")
    for action in sorted(diagnosis.recommended_actions, key=lambda item: item.priority):
        st.markdown(f"**{action.priority}. {action.title}**")
        st.write(action.description)
        st.caption(f"Estimated effort: {action.estimated_effort}")
    st.markdown("#### Caveats")
    for caveat in diagnosis.caveats:
        st.markdown(f"- {caveat}")
