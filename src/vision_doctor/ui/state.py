"""Session-state lifecycle helpers, kept independent from Streamlit globals."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from vision_doctor.models import AuditReport

REPORT_KEY = "vision_doctor_report"
WORKSPACE_KEY = "vision_doctor_workspace"
UPLOAD_TOKEN_KEY = "vision_doctor_upload_token"


def initialize_state(state: MutableMapping[str, Any]) -> None:
    """Create stable keys without overwriting an active analysis."""

    state.setdefault(REPORT_KEY, None)
    state.setdefault(WORKSPACE_KEY, None)
    state.setdefault(UPLOAD_TOKEN_KEY, None)


def clear_analysis(state: MutableMapping[str, Any]) -> None:
    """Release the old upload workspace and clear its analysis result."""

    workspace = state.get(WORKSPACE_KEY)
    if workspace is not None:
        workspace.cleanup()
    state[WORKSPACE_KEY] = None
    state[REPORT_KEY] = None


def observe_upload(state: MutableMapping[str, Any], token: str | None) -> None:
    """Clear stale data as soon as the selected upload changes."""

    initialize_state(state)
    if token != state[UPLOAD_TOKEN_KEY]:
        clear_analysis(state)
        state[UPLOAD_TOKEN_KEY] = token


def store_analysis(
    state: MutableMapping[str, Any],
    report: AuditReport,
    workspace: Any,
) -> None:
    """Replace a prior result, cleaning its temporary files first."""

    current = state.get(WORKSPACE_KEY)
    if current is not None and current is not workspace:
        current.cleanup()
    state[WORKSPACE_KEY] = workspace
    state[REPORT_KEY] = report


def current_report(state: MutableMapping[str, Any]) -> AuditReport | None:
    """Return the validated report currently held by the UI session."""

    value = state.get(REPORT_KEY)
    return value if isinstance(value, AuditReport) else None
