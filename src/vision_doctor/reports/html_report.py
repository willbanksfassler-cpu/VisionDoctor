"""Self-contained, escaped HTML presentation for VisionDoctor audits."""

from __future__ import annotations

import json
from collections import Counter
from html import escape
from pathlib import Path
from typing import Any

from vision_doctor.models import AuditReport
from vision_doctor.reports.json_report import _write_text


def _escaped(value: object) -> str:
    return escape(str(value), quote=True)


def _display(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4g}"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _cell(value: object) -> str:
    return f"<td>{_escaped(_display(value))}</td>"


def _flatten_mapping(
    value: dict[str, Any],
    prefix: str = "",
) -> list[tuple[str, object]]:
    rows: list[tuple[str, object]] = []
    for key in sorted(value):
        full_key = f"{prefix}.{key}" if prefix else key
        item = value[key]
        if isinstance(item, dict):
            rows.extend(_flatten_mapping(item, full_key))
        else:
            rows.append((full_key, item))
    return rows


def _render_overview(report: AuditReport) -> str:
    summary = report.manifest.summary
    rows = [
        ("Dataset", report.manifest.dataset_name),
        ("Source archive", report.manifest.source_archive),
        ("Images", summary.image_count),
        ("Label files", summary.label_file_count),
        ("Annotations", summary.annotation_count),
        ("Classes", summary.class_count),
        ("Issues", summary.issue_count),
        ("Dataset bytes", summary.total_size_bytes),
    ]
    body = "".join(
        f"<tr><th>{_escaped(name)}</th>{_cell(value)}</tr>" for name, value in rows
    )
    return (
        '<section><h2>Dataset overview</h2>'
        f'<table class="kv">{body}</table></section>'
    )


def _render_score(report: AuditReport) -> str:
    score = report.health_score
    penalty_rows = "".join(
        f"<tr><th>{_escaped(name)}</th>{_cell(value)}</tr>"
        for name, value in sorted(score.penalties.items())
    )
    breakdown_rows = "".join(
        "<tr>"
        + _cell(item.component)
        + _cell(item.score)
        + _cell(item.weight)
        + _cell(item.deductions)
        + "</tr>"
        for item in sorted(score.breakdown, key=lambda item: item.component)
    )
    explanations = "".join(
        f"<li>{_escaped(item)}</li>" for item in score.explanation
    )
    return (
        '<section><h2>Health Score</h2>'
        f'<div class="score"><strong>{score.overall:.2f}</strong><span>/ 100 · Grade '
        f"{_escaped(score.grade)}</span></div>"
        f"<p>{_escaped(score.disclaimer)}</p>"
        f"<p>Methodology: {_escaped(score.methodology_version)}</p>"
        '<h3>Penalty details</h3><table class="kv">'
        f"{penalty_rows}</table>"
        '<h3>Component breakdown</h3><table><thead><tr><th>Component</th>'
        '<th>Component score</th><th>Weight</th><th>Deductions</th></tr></thead>'
        f"<tbody>{breakdown_rows}</tbody></table><ul>{explanations}</ul></section>"
    )


def _render_issues(report: AuditReport) -> str:
    counts = Counter((issue.code, issue.severity.value) for issue in report.issues)
    summary_rows = "".join(
        "<tr>" + _cell(code) + _cell(severity) + _cell(count) + "</tr>"
        for (code, severity), count in sorted(counts.items())
    )
    severity_rank = {"critical": 0, "error": 1, "warning": 2, "info": 3}
    issues = sorted(
        report.issues,
        key=lambda item: (
            severity_rank[item.severity.value],
            item.code,
            item.relative_path or "",
            item.annotation_line or 0,
            item.issue_id,
        ),
    )
    detail_rows = "".join(
        "<tr>"
        + _cell(issue.code)
        + _cell(issue.severity.value)
        + _cell(issue.relative_path)
        + _cell(issue.annotation_line)
        + _cell(issue.message)
        + _cell(issue.metrics)
        + _cell(issue.suggested_action)
        + "</tr>"
        for issue in issues
    )
    if not detail_rows:
        detail_rows = '<tr><td colspan="7">No issues detected.</td></tr>'
    return (
        '<section><h2>Issue summary</h2><table><thead><tr><th>Code</th>'
        '<th>Severity</th><th>Count</th></tr></thead>'
        f"<tbody>{summary_rows}</tbody></table>"
        '<h3>Issue evidence</h3><table><thead><tr><th>Code</th><th>Severity</th>'
        '<th>Path</th><th>Line</th><th>Message</th><th>Metrics</th>'
        '<th>Suggested action</th></tr></thead>'
        f"<tbody>{detail_rows}</tbody></table></section>"
    )


def _render_distribution(report: AuditReport) -> str:
    stats = report.distribution
    class_ids = sorted(
        set(report.manifest.class_names)
        | set(stats.class_counts)
        | set(stats.class_image_counts)
    )
    rows = "".join(
        "<tr>"
        + _cell(class_id)
        + _cell(report.manifest.class_names.get(class_id, "Unknown"))
        + _cell(stats.class_counts.get(class_id, 0))
        + _cell(stats.class_image_counts.get(class_id, 0))
        + _cell(f"{stats.class_percentages.get(class_id, 0.0) * 100:.2f}%")
        + _cell(class_id in stats.rare_class_ids)
        + _cell(class_id in stats.zero_instance_class_ids)
        + "</tr>"
        for class_id in class_ids
    )
    return (
        '<section><h2>Class distribution</h2>'
        f"<p>Total annotations: {_escaped(stats.total_annotations)} · "
        f"Imbalance index: {_escaped(_display(stats.imbalance_index))} · "
        f"Rare threshold: {_escaped(_display(stats.rare_class_threshold))}</p>"
        '<table><thead><tr><th>ID</th><th>Class</th><th>Instances</th>'
        '<th>Images</th><th>Share</th><th>Rare</th><th>Zero instances</th>'
        f"</tr></thead><tbody>{rows}</tbody></table></section>"
    )


def _render_duplicates(report: AuditReport) -> str:
    rows = "".join(
        "<tr>"
        + _cell(group.group_id)
        + _cell(group.kind)
        + _cell(group.representative_image_id)
        + _cell(group.image_ids)
        + _cell(group.hamming_distance)
        + _cell(group.pair_distances)
        + "</tr>"
        for group in sorted(report.duplicate_groups, key=lambda item: item.group_id)
    )
    if not rows:
        rows = '<tr><td colspan="6">No duplicate groups detected.</td></tr>'
    return (
        '<section><h2>Duplicate groups</h2><table><thead><tr><th>Group</th>'
        '<th>Kind</th><th>Representative</th><th>Members</th>'
        '<th>Distance</th><th>Pair distances</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></section>"
    )


def _render_diagnosis(report: AuditReport) -> str:
    diagnosis = report.diagnosis
    if diagnosis is None:
        return (
            '<section><h2>Dataset Doctor diagnosis</h2>'
            '<p>Diagnosis was not requested or is not available.</p>'
            '<h3>Repair action plan</h3><p>No diagnosis-based actions available.</p>'
            '<h3>Caveats</h3><p>No diagnosis-specific caveats available.</p></section>'
        )
    findings = "".join(
        "<tr>"
        + _cell(item.rank)
        + _cell(item.severity.value)
        + _cell(item.title)
        + _cell(item.rationale)
        + _cell(item.inference)
        + _cell(item.affected_count)
        + _cell(item.score_penalty)
        + _cell(item.issue_ids)
        + "</tr>"
        for item in sorted(diagnosis.priority_findings, key=lambda item: item.rank)
    )
    actions = "".join(
        "<tr>"
        + _cell(item.priority)
        + _cell(item.title)
        + _cell(item.description)
        + _cell(item.estimated_effort)
        + _cell(item.related_issue_ids)
        + "</tr>"
        for item in sorted(diagnosis.recommended_actions, key=lambda item: item.priority)
    )
    caveats = "".join(
        f"<li>{_escaped(item)}</li>" for item in diagnosis.caveats
    )
    return (
        '<section><h2>Dataset Doctor diagnosis</h2>'
        f"<p>Generated by: {_escaped(diagnosis.generated_by)} · Risk: "
        f"{_escaped(diagnosis.risk_level)}</p><p>{_escaped(diagnosis.summary)}</p>"
        '<h3>Priority findings</h3><table><thead><tr><th>Rank</th><th>Severity</th>'
        '<th>Finding</th><th>Rationale</th><th>Inference</th><th>Affected</th>'
        '<th>Penalty</th><th>Issue IDs</th></tr></thead>'
        f"<tbody>{findings}</tbody></table>"
        '<h3>Repair action plan</h3><table><thead><tr><th>Priority</th>'
        '<th>Action</th><th>Description</th><th>Effort</th><th>Issue IDs</th>'
        f"</tr></thead><tbody>{actions}</tbody></table>"
        f"<h3>Caveats</h3><ul>{caveats}</ul></section>"
    )


def _render_thresholds(report: AuditReport) -> str:
    rows = "".join(
        f"<tr><th>{_escaped(name)}</th>{_cell(value)}</tr>"
        for name, value in _flatten_mapping(report.threshold_snapshot)
    )
    if not rows:
        rows = '<tr><td colspan="2">No threshold snapshot recorded.</td></tr>'
    return (
        '<section><h2>Threshold snapshot</h2>'
        f'<table class="kv">{rows}</table></section>'
    )


def render_html_report(report: AuditReport) -> str:
    """Render a self-contained HTML report with all dynamic text escaped."""

    metadata = (
        f"Report {_escaped(report.report_id)} · Schema {_escaped(report.schema_version)} · "
        f"Generated {_escaped(report.generated_at.isoformat())}"
    )
    sections = "".join(
        (
            _render_overview(report),
            _render_score(report),
            _render_issues(report),
            _render_distribution(report),
            _render_duplicates(report),
            _render_diagnosis(report),
            _render_thresholds(report),
        )
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VisionDoctor audit report</title>
  <style>
    :root {{ color-scheme: light; font-family: system-ui, sans-serif; color: #172033; }}
    body {{ margin: 0 auto; max-width: 1180px; padding: 2rem; background: #f4f7fb; }}
    header, section {{ background: white; border: 1px solid #dce3ee; border-radius: 12px;
      margin-bottom: 1rem; padding: 1.25rem; box-shadow: 0 2px 8px #1720330d; }}
    h1, h2, h3 {{ color: #163a63; }}
    .meta {{ color: #55657a; overflow-wrap: anywhere; }}
    .score {{ align-items: baseline; display: flex; gap: .6rem; }}
    .score strong {{ color: #0c7a65; font-size: 2.5rem; }}
    table {{ border-collapse: collapse; display: block; overflow-x: auto; width: 100%; }}
    th, td {{ border-bottom: 1px solid #e5eaf1; padding: .55rem .7rem; text-align: left;
      vertical-align: top; white-space: pre-wrap; overflow-wrap: anywhere; }}
    th {{ background: #f0f4f9; }}
    .kv th {{ width: 28%; }}
  </style>
</head>
<body>
  <header><h1>VisionDoctor audit report</h1><p class="meta">{metadata}</p></header>
  {sections}
</body>
</html>
"""


def write_html_report(report: AuditReport, destination: str | Path) -> Path:
    """Render completely, then write the self-contained HTML using UTF-8."""

    content = render_html_report(report)
    return _write_text(Path(destination), content)
