"""Dataset Doctor diagnosis presentation."""

from __future__ import annotations

import streamlit as st

from vision_doctor.models import AuditReport


def _render_repair_simulation(report: AuditReport) -> None:
    st.markdown("#### 假设修复影响预演")
    simulation = report.repair_simulation
    if simulation is None or not simulation.impacts:
        st.info("当前没有可用的修复影响预演。")
        return
    st.warning(simulation.disclaimer)
    st.dataframe(
        [
            {
                "情景": impact.scenario.title,
                "建议动作": impact.scenario.suggested_action,
                "工作量": impact.scenario.estimated_effort,
                "影响问题数": impact.affected_issue_count,
                "当前分数": impact.original_score,
                "模拟分数": impact.simulated_score,
                "分数变化": impact.score_delta,
                "需要人工确认": (
                    impact.scenario.requires_human_confirmation
                ),
            }
            for impact in simulation.impacts
        ],
        hide_index=True,
        use_container_width=True,
    )
    with st.expander("预演假设与注意事项"):
        for impact in simulation.impacts:
            st.markdown(f"**{impact.scenario.title}**")
            for assumption in impact.assumptions:
                st.markdown(f"- 假设：{assumption}")
            for caveat in impact.caveats:
                st.markdown(f"- 注意：{caveat}")


def render_doctor_panel(report: AuditReport) -> None:
    """Render assessment, risk, findings, actions, and caveats."""

    st.markdown("### Dataset Doctor")
    st.caption("基于结构化证据生成诊断结论、优先事项与修复路径")
    diagnosis = report.diagnosis
    if diagnosis is None:
        st.info("本次报告没有运行 Dataset Doctor。")
        _render_repair_simulation(report)
        return
    mode = "LLM" if diagnosis.generated_by == "llm" else "确定性诊断"
    risk_labels = {
        "low": "低",
        "medium": "中",
        "high": "高",
        "critical": "严重",
    }
    first, second = st.columns(2)
    first.metric("运行模式", mode)
    second.metric("风险等级", risk_labels[diagnosis.risk_level])
    st.caption(f"执行路径：{report.diagnosis_mode}")
    if report.diagnosis_failure_stage is not None:
        st.caption(
            "脱敏后的回退阶段："
            f"{report.diagnosis_failure_stage}"
        )
    st.markdown("#### 总体判断")
    st.write(diagnosis.summary)
    st.markdown("#### 优先问题")
    if not diagnosis.priority_findings:
        st.info("没有生成优先问题。")
    for finding in sorted(diagnosis.priority_findings, key=lambda item: item.rank):
        with st.expander(f"{finding.rank}. {finding.title}"):
            st.write(finding.rationale)
            if finding.inference:
                st.caption(f"推断：{finding.inference}")
            st.caption(
                f"严重程度：{finding.severity.value}；影响数量：{finding.affected_count}；"
                f"对应扣分：{finding.score_penalty:.2f}"
            )
    st.markdown("#### 行动计划")
    for action in sorted(diagnosis.recommended_actions, key=lambda item: item.priority):
        st.markdown(f"**{action.priority}. {action.title}**")
        st.write(action.description)
        st.caption(f"预计工作量：{action.estimated_effort}")
    st.markdown("#### 注意事项")
    for caveat in diagnosis.caveats:
        st.markdown(f"- {caveat}")
    with st.expander("结构化事实声明"):
        if diagnosis.evidence_claims:
            st.dataframe(
                [claim.model_dump(mode="json") for claim in diagnosis.evidence_claims],
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info("没有返回结构化事实声明。")
    _render_repair_simulation(report)
