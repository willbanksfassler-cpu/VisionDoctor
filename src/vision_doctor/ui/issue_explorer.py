"""Filterable issue and duplicate-image evidence explorer."""

from __future__ import annotations

import math
from pathlib import Path, PurePosixPath

import streamlit as st

from vision_doctor.models import AuditReport, ImageRecord, Issue
from vision_doctor.utils.images import render_archive_preview

_KNOWN_SPLITS = {"train", "val", "valid", "validation", "test"}
_SEVERITY_LABELS = {
    "critical": "严重",
    "error": "错误",
    "warning": "警告",
    "info": "提示",
}


def split_for_path(relative_path: str | None) -> str:
    """Infer a conventional YOLO split from a dataset-relative path."""

    if not relative_path:
        return "unknown"
    parts = [part.lower() for part in PurePosixPath(relative_path.replace("\\", "/")).parts]
    for part in parts:
        if part in _KNOWN_SPLITS:
            return "val" if part in {"valid", "validation"} else part
    return "root"


def image_for_issue(report: AuditReport, issue: Issue) -> ImageRecord | None:
    """Resolve an Issue to its image without trusting arbitrary filesystem paths."""

    by_id = {image.image_id: image for image in report.manifest.images}
    if issue.image_id in by_id:
        return by_id[issue.image_id]
    metric_path = issue.metrics.get("image_path")
    if isinstance(metric_path, str):
        for image in report.manifest.images:
            if image.relative_path == metric_path:
                return image
    if issue.relative_path:
        for image in report.manifest.images:
            if image.label_path == issue.relative_path:
                return image
    return None


def class_ids_for_issue(report: AuditReport, issue: Issue) -> set[int]:
    """Return declared or parsed classes connected to one issue."""

    class_ids: set[int] = set()
    metric_class = issue.metrics.get("class_id")
    if isinstance(metric_class, int):
        class_ids.add(metric_class)
    image = image_for_issue(report, issue)
    if image is not None:
        class_ids.update(
            annotation.class_id
            for annotation in report.manifest.annotations
            if annotation.image_id == image.image_id
        )
    return class_ids


def filter_issues(
    report: AuditReport,
    *,
    codes: set[str] | None = None,
    severities: set[str] | None = None,
    splits: set[str] | None = None,
    class_ids: set[int] | None = None,
) -> list[Issue]:
    """Apply the Issue Explorer's four filters deterministically."""

    selected: list[Issue] = []
    for issue in report.issues:
        image = image_for_issue(report, issue)
        path = image.relative_path if image is not None else issue.relative_path
        if codes and issue.code not in codes:
            continue
        if severities and issue.severity.value not in severities:
            continue
        if splits and split_for_path(path) not in splits:
            continue
        if class_ids and not (class_ids_for_issue(report, issue) & class_ids):
            continue
        selected.append(issue)
    severity_rank = {"critical": 0, "error": 1, "warning": 2, "info": 3}
    return sorted(
        selected,
        key=lambda item: (
            severity_rank[item.severity.value],
            item.code,
            item.relative_path or "",
            item.annotation_line or 0,
        ),
    )


def _threshold_metrics(issue: Issue) -> dict[str, object]:
    return {
        key: value
        for key, value in issue.metrics.items()
        if "threshold" in key or key.startswith("min_")
    }


def _render_issue(
    report: AuditReport,
    issue: Issue,
    archive_path: Path | None,
) -> None:
    path = issue.relative_path or "数据集级别"
    with st.expander(
        f"{_SEVERITY_LABELS[issue.severity.value]} · {issue.code} · {path}"
    ):
        st.caption("检测器原始说明")
        st.write(issue.message)
        image = image_for_issue(report, issue)
        if image is not None and archive_path is not None:
            boxes = [issue.bbox] if issue.bbox is not None else []
            preview = render_archive_preview(
                archive_path,
                image.relative_path,
                bboxes=boxes,
            )
            if preview is None:
                st.info("图片无法预览，但结构化证据仍然有效。")
            else:
                st.image(preview, caption=image.relative_path, use_container_width=True)
        elif issue.image_id or issue.relative_path:
            st.info("该问题没有可用的图片预览。")
        details = {
            "标签行号": issue.annotation_line,
            "边界框": issue.bbox,
            "数据划分": split_for_path(image.relative_path if image else path),
            "类别 ID": sorted(class_ids_for_issue(report, issue)),
            "测量指标": issue.metrics,
            "使用阈值": _threshold_metrics(issue),
            "建议动作": issue.suggested_action,
        }
        st.json(details)


def _render_duplicates(report: AuditReport, archive_path: Path | None) -> None:
    st.subheader("重复图片组")
    if not report.duplicate_groups:
        st.info("没有检测到完全重复或近似重复图片组。")
        return
    images = {image.image_id: image for image in report.manifest.images}
    for group in report.duplicate_groups:
        with st.expander(
            f"{group.kind.upper()} 组 · {len(group.image_ids)} 张图片 · {group.group_id}"
        ):
            st.caption(
                f"代表图片：{group.representative_image_id or '未设置'}；"
                "pHash 距离："
                f"{group.hamming_distance if group.hamming_distance is not None else '不适用'}"
            )
            columns = st.columns(min(len(group.image_ids), 3))
            for index, image_id in enumerate(group.image_ids):
                record = images.get(image_id)
                with columns[index % len(columns)]:
                    if record is None or archive_path is None:
                        st.info(f"无法预览 {image_id}。")
                        continue
                    preview = render_archive_preview(archive_path, record.relative_path)
                    if preview is None:
                        st.info(f"无法预览 {record.relative_path}。")
                    else:
                        st.image(
                            preview,
                            caption=record.relative_path,
                            use_container_width=True,
                        )


def render_issue_explorer(
    report: AuditReport,
    archive_path: str | Path | None,
) -> None:
    """Render filters, paginated issues, image evidence, and duplicate groups."""

    st.subheader("问题浏览器")
    filter_columns = st.columns(4)
    code_options = sorted({issue.code for issue in report.issues})
    severity_options = ["critical", "error", "warning", "info"]
    split_options: set[str] = set()
    for issue in report.issues:
        linked_image = image_for_issue(report, issue)
        split_options.add(
            split_for_path(
                linked_image.relative_path if linked_image else issue.relative_path
            )
        )
    class_options = sorted(
        set(report.manifest.class_names).union(
            *(class_ids_for_issue(report, issue) for issue in report.issues)
        )
    )
    codes = set(filter_columns[0].multiselect("问题代码", code_options))
    selected_severity_labels = filter_columns[1].multiselect(
        "严重程度",
        [_SEVERITY_LABELS[item] for item in severity_options],
    )
    severities = {
        value
        for value, label in _SEVERITY_LABELS.items()
        if label in selected_severity_labels
    }
    splits = set(filter_columns[2].multiselect("数据划分", sorted(split_options)))
    class_labels = {
        class_id: f"{class_id}: {report.manifest.class_names.get(class_id, '未声明')}"
        for class_id in class_options
    }
    selected_class_labels = filter_columns[3].multiselect(
        "类别",
        [class_labels[class_id] for class_id in class_options],
    )
    selected_classes = {
        class_id
        for class_id, label in class_labels.items()
        if label in selected_class_labels
    }
    filtered = filter_issues(
        report,
        codes=codes,
        severities=severities,
        splits=splits,
        class_ids=selected_classes,
    )
    page_size = int(
        st.number_input("每页问题数", min_value=5, max_value=50, value=10, step=5)
    )
    page_count = max(1, math.ceil(len(filtered) / page_size))
    page = int(
        st.number_input("页码", min_value=1, max_value=page_count, value=1, step=1)
    )
    st.caption(f"共找到 {len(filtered)} 个匹配问题，当前第 {page}/{page_count} 页。")
    start = (page - 1) * page_size
    resolved_archive = Path(archive_path) if archive_path is not None else None
    for issue in filtered[start : start + page_size]:
        _render_issue(report, issue, resolved_archive)
    _render_duplicates(report, resolved_archive)
