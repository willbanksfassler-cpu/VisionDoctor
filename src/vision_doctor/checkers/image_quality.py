"""Deterministic fixed or split-adaptive image-quality checks."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from vision_doctor.config import ImageQualityThresholds
from vision_doctor.models import DatasetManifest, ImageRecord, Issue, Severity
from vision_doctor.utils.images import ImageMeasurements, decode_image, measure_image

IMAGE_UNREADABLE = "IMAGE_UNREADABLE"
IMAGE_BLURRY = "IMAGE_BLURRY"
IMAGE_DARK = "IMAGE_DARK"
IMAGE_BRIGHT = "IMAGE_BRIGHT"
IMAGE_LOW_RESOLUTION = "IMAGE_LOW_RESOLUTION"

_EPSILON = 1e-12


@dataclass(frozen=True)
class _MeasuredRecord:
    record: ImageRecord
    measurements: ImageMeasurements


@dataclass(frozen=True)
class _ThresholdDecision:
    fixed_threshold: float
    adaptive_threshold: float | None
    effective_threshold: float
    threshold_source: str
    sample_count: int
    median: float | None = None
    mad: float | None = None
    iqr: float | None = None


def _issue_id(code: str, relative_path: str) -> str:
    payload = json.dumps([code, relative_path], separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"image-quality-{digest}"


def _split_for_path(relative_path: str) -> str:
    first = relative_path.replace("\\", "/").split("/", maxsplit=1)[0].casefold()
    return first if first in {"train", "val", "test"} else "root"


def _issue(
    *,
    code: str,
    severity: Severity,
    message: str,
    relative_path: str,
    image_id: str,
    metrics: dict[str, int | float | str | None],
    suggested_action: str,
) -> Issue:
    return Issue(
        issue_id=_issue_id(code, relative_path),
        code=code,
        severity=severity,
        message=message,
        relative_path=relative_path,
        image_id=image_id,
        metrics=metrics,
        suggested_action=suggested_action,
        evidence={"path": relative_path, "metrics": metrics},
    )


def _fixed_decision(fixed: float, sample_count: int) -> _ThresholdDecision:
    return _ThresholdDecision(
        fixed_threshold=fixed,
        adaptive_threshold=None,
        effective_threshold=fixed,
        threshold_source="fixed",
        sample_count=sample_count,
    )


def _adaptive_decision(
    values: list[float],
    *,
    fixed: float,
    lower_bound: float,
    upper_bound: float,
    direction: str,
    config: ImageQualityThresholds,
) -> _ThresholdDecision:
    sample_count = len(values)
    if config.mode == "fixed":
        return _fixed_decision(fixed, sample_count)
    if sample_count < config.adaptive_min_samples:
        return _ThresholdDecision(
            fixed_threshold=fixed,
            adaptive_threshold=None,
            effective_threshold=fixed,
            threshold_source="fixed_fallback_insufficient_samples",
            sample_count=sample_count,
        )

    array = np.asarray(values, dtype=float)
    median = float(np.median(array))
    mad = float(np.median(np.abs(array - median)))
    q1, q3 = np.percentile(array, [25, 75])
    iqr = float(q3 - q1)
    if mad > _EPSILON:
        spread = 1.4826 * mad
        source = "adaptive_mad"
    elif iqr > _EPSILON:
        spread = iqr / 1.349
        source = "adaptive_iqr"
    else:
        return _ThresholdDecision(
            fixed_threshold=fixed,
            adaptive_threshold=None,
            effective_threshold=fixed,
            threshold_source="fixed_fallback_zero_dispersion",
            sample_count=sample_count,
            median=median,
            mad=mad,
            iqr=iqr,
        )
    sign = -1.0 if direction == "lower" else 1.0
    candidate = median + sign * config.adaptive_mad_multiplier * spread
    adaptive = min(max(candidate, lower_bound), upper_bound)
    return _ThresholdDecision(
        fixed_threshold=fixed,
        adaptive_threshold=adaptive,
        effective_threshold=adaptive,
        threshold_source=source,
        sample_count=sample_count,
        median=median,
        mad=mad,
        iqr=iqr,
    )


def _decision_metrics(
    measured_value: float,
    decision: _ThresholdDecision,
) -> dict[str, int | float | str | None]:
    return {
        "measured_value": measured_value,
        "fixed_threshold": decision.fixed_threshold,
        "adaptive_threshold": decision.adaptive_threshold,
        "effective_threshold": decision.effective_threshold,
        "threshold_source": decision.threshold_source,
        "sample_count": decision.sample_count,
        "calibration_median": decision.median,
        "calibration_mad": decision.mad,
        "calibration_iqr": decision.iqr,
    }


def _calibrate_split(
    records: list[_MeasuredRecord],
    config: ImageQualityThresholds,
) -> dict[str, _ThresholdDecision]:
    brightness = [item.measurements.grayscale_mean for item in records]
    sharpness = [item.measurements.laplacian_variance for item in records]
    dimensions = [
        float(min(item.measurements.width, item.measurements.height))
        for item in records
    ]
    fixed_dimension = float(min(config.min_width, config.min_height))
    return {
        "blur": _adaptive_decision(
            sharpness,
            fixed=config.blur_variance_threshold,
            lower_bound=config.adaptive_blur_min,
            upper_bound=config.adaptive_blur_max,
            direction="lower",
            config=config,
        ),
        "dark": _adaptive_decision(
            brightness,
            fixed=config.dark_mean_threshold,
            lower_bound=config.adaptive_dark_min,
            upper_bound=config.adaptive_dark_max,
            direction="lower",
            config=config,
        ),
        "bright": _adaptive_decision(
            brightness,
            fixed=config.bright_mean_threshold,
            lower_bound=config.adaptive_bright_min,
            upper_bound=config.adaptive_bright_max,
            direction="upper",
            config=config,
        ),
        "dimension": _adaptive_decision(
            dimensions,
            fixed=fixed_dimension,
            lower_bound=config.adaptive_dimension_min,
            upper_bound=config.adaptive_dimension_max,
            direction="lower",
            config=config,
        ),
    }


def check_image_quality(
    manifest: DatasetManifest,
    dataset_root: str | Path,
    *,
    config: ImageQualityThresholds | None = None,
) -> list[Issue]:
    """Measure images, calibrate per split, and isolate unreadable files."""

    active = config or ImageQualityThresholds()
    root = Path(dataset_root)
    measured_by_split: dict[str, list[_MeasuredRecord]] = defaultdict(list)
    newly_unreadable: list[ImageRecord] = []
    for record in manifest.images:
        image = decode_image(root / Path(record.relative_path))
        if image is None:
            newly_unreadable.append(record)
            continue
        measured_by_split[_split_for_path(record.relative_path)].append(
            _MeasuredRecord(record=record, measurements=measure_image(image))
        )
    calibrations = {
        split: _calibrate_split(records, active)
        for split, records in measured_by_split.items()
    }

    issues: list[Issue] = []
    unreadable = [(path, path) for path in manifest.unreadable_image_paths] + [
        (record.relative_path, record.image_id) for record in newly_unreadable
    ]
    for relative_path, image_id in unreadable:
        split = _split_for_path(relative_path)
        sample_count = len(measured_by_split.get(split, []))
        issues.append(
            _issue(
                code=IMAGE_UNREADABLE,
                severity=Severity.ERROR,
                message="Image could not be decoded.",
                relative_path=relative_path,
                image_id=image_id,
                metrics={
                    "decoded": "false",
                    "measured_value": None,
                    "fixed_threshold": None,
                    "adaptive_threshold": None,
                    "effective_threshold": None,
                    "threshold_source": "not_applicable_unreadable",
                    "sample_count": sample_count,
                },
                suggested_action="Replace or re-export the damaged image file.",
            )
        )

    for split, records in measured_by_split.items():
        decisions = calibrations[split]
        for item in records:
            record = item.record
            measured = item.measurements
            common = {
                "width": measured.width,
                "height": measured.height,
                "grayscale_mean": measured.grayscale_mean,
                "laplacian_variance": measured.laplacian_variance,
            }
            blur = decisions["blur"]
            if measured.laplacian_variance < blur.effective_threshold:
                issues.append(
                    _issue(
                        code=IMAGE_BLURRY,
                        severity=Severity.WARNING,
                        message="Image sharpness is below the effective threshold.",
                        relative_path=record.relative_path,
                        image_id=record.image_id,
                        metrics={
                            **common,
                            "blur_variance_threshold": blur.effective_threshold,
                            **_decision_metrics(
                                measured.laplacian_variance,
                                blur,
                            ),
                        },
                        suggested_action=(
                            "Review focus and replace the image if detail is lost."
                        ),
                    )
                )
            dark = decisions["dark"]
            if measured.grayscale_mean < dark.effective_threshold:
                issues.append(
                    _issue(
                        code=IMAGE_DARK,
                        severity=Severity.WARNING,
                        message="Image brightness is below the effective dark threshold.",
                        relative_path=record.relative_path,
                        image_id=record.image_id,
                        metrics={
                            **common,
                            "dark_mean_threshold": dark.effective_threshold,
                            **_decision_metrics(measured.grayscale_mean, dark),
                        },
                        suggested_action=(
                            "Review exposure and replace or correct the source image."
                        ),
                    )
                )
            bright = decisions["bright"]
            if measured.grayscale_mean > bright.effective_threshold:
                issues.append(
                    _issue(
                        code=IMAGE_BRIGHT,
                        severity=Severity.WARNING,
                        message=(
                            "Image brightness exceeds the effective bright threshold."
                        ),
                        relative_path=record.relative_path,
                        image_id=record.image_id,
                        metrics={
                            **common,
                            "bright_mean_threshold": bright.effective_threshold,
                            **_decision_metrics(measured.grayscale_mean, bright),
                        },
                        suggested_action=(
                            "Review exposure and replace or correct the source image."
                        ),
                    )
                )
            dimension = decisions["dimension"]
            min_dimension = float(min(measured.width, measured.height))
            fixed_fallback = dimension.threshold_source.startswith("fixed")
            if fixed_fallback:
                too_small = (
                    measured.width < active.min_width
                    or measured.height < active.min_height
                )
            else:
                too_small = min_dimension < dimension.effective_threshold
            if too_small:
                issues.append(
                    _issue(
                        code=IMAGE_LOW_RESOLUTION,
                        severity=Severity.WARNING,
                        message="Image dimensions are below the effective minimum.",
                        relative_path=record.relative_path,
                        image_id=record.image_id,
                        metrics={
                            **common,
                            "min_width": active.min_width,
                            "min_height": active.min_height,
                            **_decision_metrics(min_dimension, dimension),
                        },
                        suggested_action=(
                            "Use a higher-resolution source image when available."
                        ),
                    )
                )
    return sorted(issues, key=lambda issue: (issue.relative_path or "", issue.code))
