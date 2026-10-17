"""UTF-8 JSON serialization for :class:`~vision_doctor.models.AuditReport`."""

from __future__ import annotations

import json
from pathlib import Path

from vision_doctor.models import AuditReport


def render_json_report(report: AuditReport, *, indent: int = 2) -> str:
    """Render a complete report with stable object-key ordering."""

    payload = report.model_dump(mode="json")
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=indent,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"


def _write_text(destination: Path, content: str) -> Path:
    """Write content that has already been rendered completely in memory."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open(mode="w", encoding="utf-8", newline="\n") as output:
        output.write(content)
    return destination


def write_json_report(report: AuditReport, destination: str | Path) -> Path:
    """Render completely, then write the JSON report using UTF-8."""

    content = render_json_report(report)
    return _write_text(Path(destination), content)


def load_json_report(source: str | Path) -> AuditReport:
    """Read a UTF-8 JSON report and validate it against the current contract."""

    return AuditReport.model_validate_json(Path(source).read_text(encoding="utf-8"))
