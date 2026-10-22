"""Top-level Streamlit page and dataset summary dashboard."""

from __future__ import annotations

from collections import Counter

import streamlit as st

from vision_doctor.config import Settings
from vision_doctor.models import AuditReport
from vision_doctor.ui.doctor_panel import render_doctor_panel
from vision_doctor.ui.issue_explorer import render_issue_explorer
from vision_doctor.ui.report_panel import render_report_panel
from vision_doctor.ui.state import current_report, initialize_state
from vision_doctor.ui.theme import apply_theme
from vision_doctor.ui.upload import render_upload

TAB_LABELS = ("上传数据", "健康看板", "问题浏览器", "AI 诊断与报告")


def render_dashboard(report: AuditReport) -> None:
    """Render score, counts, distribution, penalties, and quality summary."""

    summary = report.manifest.summary
    columns = st.columns(5)
    columns[0].metric("健康分", f"{report.health_score.overall:.1f}/100")
    columns[1].metric("图片数", summary.image_count)
    columns[2].metric("标签文件", summary.label_file_count)
    columns[3].metric("目标实例", summary.annotation_count)
    columns[4].metric("类别数", summary.class_count)
    st.caption("健康分是启发式数据风险指标，不代表模型精度，也不保证修复后 mAP 提升。")
    st.caption(
        "评分方案："
        f"{report.health_score.profile_name} "
        f"({report.health_score.methodology_version})"
    )

    severity_counts = Counter(issue.severity.value for issue in report.issues)
    st.subheader("问题严重程度")
    severity_columns = st.columns(4)
    for column, severity in zip(
        severity_columns,
        ("critical", "error", "warning", "info"),
        strict=True,
    ):
        labels = {
            "critical": "严重",
            "error": "错误",
            "warning": "警告",
            "info": "提示",
        }
        column.metric(labels[severity], severity_counts[severity])

    left, right = st.columns(2)
    class_rows = [
        {
            "类别": report.manifest.class_names.get(class_id, str(class_id)),
            "实例数": count,
        }
        for class_id, count in sorted(report.distribution.class_counts.items())
    ]
    with left:
        st.subheader("类别分布")
        if class_rows:
            st.bar_chart(class_rows, x="类别", y="实例数")
        else:
            st.info("没有解析到类别实例。")
    with right:
        st.subheader("扣分构成")
        penalty_rows = [
            {"扣分项": name, "分值": value}
            for name, value in sorted(report.health_score.penalties.items())
        ]
        st.bar_chart(penalty_rows, x="扣分项", y="分值")

    quality_counts = Counter(
        issue.code for issue in report.issues if issue.code.startswith("IMAGE_")
    )
    st.subheader("图片质量问题")
    if quality_counts:
        st.dataframe(
            [
                {"问题代码": code, "影响数量": count}
                for code, count in sorted(quality_counts.items())
            ],
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.success("没有检测到已配置的图片质量问题。")


def _empty_tab(message: str) -> None:
    st.info(message)


def render_app() -> None:
    """Render the one-page, four-tab VisionDoctor application."""

    initialize_state(st.session_state)
    settings = Settings()
    apply_theme()
    st.title("VisionDoctor")
    st.caption("AI 视觉数据集体检与修复决策助手")
    upload_tab, dashboard_tab, issues_tab, doctor_tab = st.tabs(TAB_LABELS)
    with upload_tab:
        render_upload(settings)
    report = current_report(st.session_state)
    with dashboard_tab:
        if report is None:
            _empty_tab("请先上传并分析数据集，再查看健康看板。")
        else:
            render_dashboard(report)
    with issues_tab:
        if report is None:
            _empty_tab("请先上传并分析数据集，再浏览具体问题。")
        else:
            workspace = st.session_state.get("vision_doctor_workspace")
            archive_path = workspace.archive_path if workspace is not None else None
            render_issue_explorer(report, archive_path)
    with doctor_tab:
        if report is None:
            _empty_tab("请先上传并分析数据集，再查看 AI 诊断与报告。")
        else:
            render_doctor_panel(report)
            render_report_panel(report)
