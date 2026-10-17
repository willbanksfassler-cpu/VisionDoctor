"""In-memory JSON and HTML download controls."""

from __future__ import annotations

import streamlit as st

from vision_doctor.models import AuditReport
from vision_doctor.reports import render_html_report, render_json_report


def build_report_downloads(report: AuditReport) -> tuple[bytes, bytes]:
    """Build non-empty, UTF-8 report payloads from the same AuditReport."""

    return (
        render_json_report(report).encode("utf-8"),
        render_html_report(report).encode("utf-8"),
    )


def render_report_panel(report: AuditReport) -> None:
    """Render JSON and HTML report downloads."""

    st.subheader("Download reports")
    json_payload, html_payload = build_report_downloads(report)
    columns = st.columns(2)
    columns[0].download_button(
        "Download JSON",
        data=json_payload,
        file_name="visiondoctor-audit.json",
        mime="application/json",
        use_container_width=True,
    )
    columns[1].download_button(
        "Download HTML",
        data=html_payload,
        file_name="visiondoctor-audit.html",
        mime="text/html",
        use_container_width=True,
    )
