"""Class-conditional robust statistics for valid bounding boxes."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from vision_doctor.config import BBoxOutlierConfig
from vision_doctor.models import AnnotationRecord, DatasetManifest, Issue, Severity

BBOX_AREA_OUTLIER = "BBOX_AREA_OUTLIER"
BBOX_ASPECT_RATIO_OUTLIER = "BBOX_ASPECT_RATIO_OUTLIER"

_EPSILON = 1e-12


@dataclass(frozen=True)
class _RobustProfile:
    median_log: float
    mad_log: float
    iqr_log: float
    scale: float | None
    method: str


def _profile(values: list[float]) -> _RobustProfile:
    median_log = statistics.median(values)
    deviations = [abs(value - median_log) for value in values]
    mad_log = statistics.median(deviations)
    q1, q3 = np.percentile(np.asarray(values, dtype=float), [25, 75])
    iqr_log = float(q3 - q1)
    if mad_log > _EPSILON:
        return _RobustProfile(
            median_log=median_log,
            mad_log=mad_log,
            iqr_log=iqr_log,
            scale=1.4826 * mad_log,
            method="class_log_mad",
        )
    if iqr_log > _EPSILON:
        return _RobustProfile(
            median_log=median_log,
            mad_log=mad_log,
            iqr_log=iqr_log,
            scale=iqr_log / 1.349,
            method="class_log_iqr",
        )
    return _RobustProfile(
        median_log=median_log,
        mad_log=mad_log,
        iqr_log=iqr_log,
        scale=None,
        method="class_zero_dispersion_log_ratio",
    )


def _issue_id(code: str, annotation: AnnotationRecord) -> str:
    payload = json.dumps(
        [code, annotation.source_path, annotation.line_number, annotation.bbox.root],
        separators=(",", ":"),
    )
    return f"bbox-outlier-{hashlib.sha256(payload.encode()).hexdigest()[:20]}"


def _score(
    value_log: float,
    profile: _RobustProfile,
    config: BBoxOutlierConfig,
) -> tuple[float, float]:
    distance = abs(value_log - profile.median_log)
    if profile.scale is None:
        return distance, config.zero_dispersion_log_ratio_threshold
    return distance / profile.scale, config.robust_z_threshold


def _make_issue(
    *,
    code: str,
    metric_name: str,
    measured_value: float,
    annotation: AnnotationRecord,
    sample_count: int,
    profile: _RobustProfile,
    score: float,
    threshold: float,
) -> Issue:
    metrics = {
        "class_id": annotation.class_id,
        "sample_count": sample_count,
        "metric_name": metric_name,
        "measured_value": measured_value,
        "median": math.exp(profile.median_log),
        "mad_log": profile.mad_log,
        "iqr_log": profile.iqr_log,
        "outlier_score": score,
        "outlier_threshold": threshold,
        "statistic_method": profile.method,
        "requires_human_confirmation": True,
    }
    description = "area" if metric_name == "normalized_area" else "aspect ratio"
    return Issue(
        issue_id=_issue_id(code, annotation),
        code=code,
        severity=Severity.WARNING,
        message=(
            f"Bounding-box {description} is a class-conditional statistical "
            "outlier and requires human confirmation."
        ),
        relative_path=annotation.source_path,
        image_id=annotation.image_id,
        annotation_line=annotation.line_number,
        bbox=annotation.bbox.root,
        metrics=metrics,
        suggested_action=(
            "Review the box against other instances of the same class before "
            "changing the annotation."
        ),
        evidence={
            "path": annotation.source_path,
            "line_number": annotation.line_number,
            "bbox": list(annotation.bbox.root),
            "metrics": metrics,
        },
    )


def check_bbox_outliers(
    manifest: DatasetManifest,
    *,
    config: BBoxOutlierConfig | None = None,
) -> list[Issue]:
    """Detect area and aspect-ratio candidates within each declared class."""

    active = config or BBoxOutlierConfig()
    if not active.enabled:
        return []
    by_class: dict[int, list[AnnotationRecord]] = defaultdict(list)
    for annotation in manifest.annotations:
        by_class[annotation.class_id].append(annotation)

    issues: list[Issue] = []
    for class_annotations in by_class.values():
        if len(class_annotations) < active.min_samples_per_class:
            continue
        areas = [
            item.bbox.width * item.bbox.height for item in class_annotations
        ]
        aspects = [
            item.bbox.width / item.bbox.height for item in class_annotations
        ]
        area_logs = [math.log(value) for value in areas]
        aspect_logs = [math.log(value) for value in aspects]
        area_profile = _profile(area_logs)
        aspect_profile = _profile(aspect_logs)

        for annotation, area, area_log, aspect, aspect_log in zip(
            class_annotations,
            areas,
            area_logs,
            aspects,
            aspect_logs,
            strict=True,
        ):
            area_score, area_threshold = _score(area_log, area_profile, active)
            if area_score >= area_threshold:
                issues.append(
                    _make_issue(
                        code=BBOX_AREA_OUTLIER,
                        metric_name="normalized_area",
                        measured_value=area,
                        annotation=annotation,
                        sample_count=len(class_annotations),
                        profile=area_profile,
                        score=area_score,
                        threshold=area_threshold,
                    )
                )
            aspect_score, aspect_threshold = _score(
                aspect_log,
                aspect_profile,
                active,
            )
            if aspect_score >= aspect_threshold:
                issues.append(
                    _make_issue(
                        code=BBOX_ASPECT_RATIO_OUTLIER,
                        metric_name="width_to_height_ratio",
                        measured_value=aspect,
                        annotation=annotation,
                        sample_count=len(class_annotations),
                        profile=aspect_profile,
                        score=aspect_score,
                        threshold=aspect_threshold,
                    )
                )
    return sorted(
        issues,
        key=lambda issue: (
            issue.code,
            issue.relative_path or "",
            issue.annotation_line or 0,
        ),
    )
