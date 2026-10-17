"""Deterministic image-quality checks over a parsed dataset manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from vision_doctor.config import ImageQualityThresholds
from vision_doctor.models import DatasetManifest, Issue, Severity
from vision_doctor.utils.images import decode_image, measure_image

IMAGE_UNREADABLE = "IMAGE_UNREADABLE"
IMAGE_BLURRY = "IMAGE_BLURRY"
IMAGE_DARK = "IMAGE_DARK"
IMAGE_BRIGHT = "IMAGE_BRIGHT"
IMAGE_LOW_RESOLUTION = "IMAGE_LOW_RESOLUTION"


def _issue_id(code: str, relative_path: str) -> str:
    payload = json.dumps([code, relative_path], separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"image-quality-{digest}"


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


def check_image_quality(
    manifest: DatasetManifest,
    dataset_root: str | Path,
    *,
    config: ImageQualityThresholds | None = None,
) -> list[Issue]:
    """Measure every image independently; unreadable files do not stop the scan."""

    active = config or ImageQualityThresholds()
    root = Path(dataset_root)
    issues: list[Issue] = []
    for relative_path in manifest.unreadable_image_paths:
        issues.append(
            _issue(
                code=IMAGE_UNREADABLE,
                severity=Severity.ERROR,
                message="Image could not be decoded.",
                relative_path=relative_path,
                image_id=relative_path,
                metrics={"decoded": "false"},
                suggested_action="Replace or re-export the damaged image file.",
            )
        )
    for record in manifest.images:
        image = decode_image(root / Path(record.relative_path))
        if image is None:
            issues.append(
                _issue(
                    code=IMAGE_UNREADABLE,
                    severity=Severity.ERROR,
                    message="Image could not be decoded.",
                    relative_path=record.relative_path,
                    image_id=record.image_id,
                    metrics={"decoded": "false"},
                    suggested_action="Replace or re-export the damaged image file.",
                )
            )
            continue

        measured = measure_image(image)
        common = {
            "width": measured.width,
            "height": measured.height,
            "grayscale_mean": measured.grayscale_mean,
            "laplacian_variance": measured.laplacian_variance,
        }
        if measured.laplacian_variance < active.blur_variance_threshold:
            issues.append(
                _issue(
                    code=IMAGE_BLURRY,
                    severity=Severity.WARNING,
                    message="Image sharpness is below the configured threshold.",
                    relative_path=record.relative_path,
                    image_id=record.image_id,
                    metrics={
                        **common,
                        "blur_variance_threshold": active.blur_variance_threshold,
                    },
                    suggested_action="Review focus and replace the image if detail is lost.",
                )
            )
        if measured.grayscale_mean < active.dark_mean_threshold:
            issues.append(
                _issue(
                    code=IMAGE_DARK,
                    severity=Severity.WARNING,
                    message="Image brightness is below the configured dark threshold.",
                    relative_path=record.relative_path,
                    image_id=record.image_id,
                    metrics={**common, "dark_mean_threshold": active.dark_mean_threshold},
                    suggested_action="Review exposure and replace or correct the source image.",
                )
            )
        if measured.grayscale_mean > active.bright_mean_threshold:
            issues.append(
                _issue(
                    code=IMAGE_BRIGHT,
                    severity=Severity.WARNING,
                    message="Image brightness exceeds the configured bright threshold.",
                    relative_path=record.relative_path,
                    image_id=record.image_id,
                    metrics={
                        **common,
                        "bright_mean_threshold": active.bright_mean_threshold,
                    },
                    suggested_action="Review exposure and replace or correct the source image.",
                )
            )
        if measured.width < active.min_width or measured.height < active.min_height:
            issues.append(
                _issue(
                    code=IMAGE_LOW_RESOLUTION,
                    severity=Severity.WARNING,
                    message="Image dimensions are below the configured minimum.",
                    relative_path=record.relative_path,
                    image_id=record.image_id,
                    metrics={
                        **common,
                        "min_width": active.min_width,
                        "min_height": active.min_height,
                    },
                    suggested_action="Use a higher-resolution source image when available.",
                )
            )
    return issues
