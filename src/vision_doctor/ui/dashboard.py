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
from vision_doctor.ui.upload import render_upload

TAB_LABELS = ("Upload", "Dashboard", "Issue Explorer", "AI Doctor & Report")


def render_dashboard(report: AuditReport) -> None:
    """Render score, counts, distribution, penalties, and quality summary."""

    summary = report.manifest.summary
    columns = st.columns(5)
    columns[0].metric("Health Score", f"{report.health_score.overall:.1f}/100")
    columns[1].metric("Images", summary.image_count)
    columns[2].metric("Labels", summary.label_file_count)
    columns[3].metric("Objects", summary.annotation_count)
    columns[4].metric("Classes", summary.class_count)
    st.caption(report.health_score.disclaimer)

    severity_counts = Counter(issue.severity.value for issue in report.issues)
    st.subheader("Issues by severity")
    severity_columns = st.columns(4)
    for column, severity in zip(
        severity_columns,
        ("critical", "error", "warning", "info"),
        strict=True,
    ):
        column.metric(severity.title(), severity_counts[severity])

    left, right = st.columns(2)
    class_rows = [
        {
            "class": report.manifest.class_names.get(class_id, str(class_id)),
            "instances": count,
        }
        for class_id, count in sorted(report.distribution.class_counts.items())
    ]
    with left:
        st.subheader("Class distribution")
        if class_rows:
            st.bar_chart(class_rows, x="class", y="instances")
        else:
            st.info("No class instances were parsed.")
    with right:
        st.subheader("Penalty composition")
        penalty_rows = [
            {"component": name, "points": value}
            for name, value in sorted(report.health_score.penalties.items())
        ]
        st.bar_chart(penalty_rows, x="component", y="points")

    quality_counts = Counter(
        issue.code for issue in report.issues if issue.code.startswith("IMAGE_")
    )
    st.subheader("Image quality findings")
    if quality_counts:
        st.dataframe(
            [
                {"issue": code, "affected": count}
                for code, count in sorted(quality_counts.items())
            ],
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.success("No configured image-quality issue was detected.")


def _empty_tab(message: str) -> None:
    st.info(message)


def render_app() -> None:
    """Render the one-page, four-tab VisionDoctor application."""

    initialize_state(st.session_state)
    settings = Settings()
    st.title("VisionDoctor")
    st.caption("AI-assisted visual dataset health checks and repair decisions")
    upload_tab, dashboard_tab, issues_tab, doctor_tab = st.tabs(TAB_LABELS)
    with upload_tab:
        render_upload(settings)
    report = current_report(st.session_state)
    with dashboard_tab:
        if report is None:
            _empty_tab("Upload and analyze a dataset to view its dashboard.")
        else:
            render_dashboard(report)
    with issues_tab:
        if report is None:
            _empty_tab("Upload and analyze a dataset to explore issues.")
        else:
            workspace = st.session_state.get("vision_doctor_workspace")
            archive_path = workspace.archive_path if workspace is not None else None
            render_issue_explorer(report, archive_path)
    with doctor_tab:
        if report is None:
            _empty_tab("Upload and analyze a dataset to view diagnosis and reports.")
        else:
            render_doctor_panel(report)
            render_report_panel(report)
