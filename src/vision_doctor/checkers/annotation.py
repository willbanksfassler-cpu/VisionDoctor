"""Pure annotation issue detection over a parsed dataset manifest."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from vision_doctor.models import (
    AnnotationRecord,
    DatasetManifest,
    ImageRecord,
    Issue,
    ParseErrorRecord,
    Severity,
)

LABEL_MISSING = "LABEL_MISSING"
LABEL_ORPHAN = "LABEL_ORPHAN"
LABEL_EMPTY = "LABEL_EMPTY"
LABEL_PARSE_ERROR = "LABEL_PARSE_ERROR"
CLASS_ID_INVALID = "CLASS_ID_INVALID"
BBOX_NON_POSITIVE = "BBOX_NON_POSITIVE"
BBOX_OUT_OF_RANGE = "BBOX_OUT_OF_RANGE"
BBOX_CROSSES_BORDER = "BBOX_CROSSES_BORDER"
BBOX_TINY = "BBOX_TINY"


@dataclass(frozen=True)
class AnnotationCheckConfig:
    """Configurable pixel thresholds for a potentially unusable tiny box."""

    min_bbox_width_pixels: float = 2.0
    min_bbox_height_pixels: float = 2.0
    min_bbox_area_pixels: float = 16.0

    def __post_init__(self) -> None:
        values = (
            self.min_bbox_width_pixels,
            self.min_bbox_height_pixels,
            self.min_bbox_area_pixels,
        )
        if any(value < 0.0 for value in values):
            raise ValueError("Tiny bounding-box thresholds must be non-negative.")


def _stable_issue_id(
    code: str,
    relative_path: str,
    line_number: int | None,
    bbox: tuple[float, float, float, float] | None,
) -> str:
    identity = json.dumps(
        [code, relative_path, line_number, bbox],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return f"annotation-{digest}"


def _expected_label_path(image_path: str) -> str:
    parts = image_path.split("/")
    if parts and parts[0].casefold() == "images":
        parts[0] = "labels"
    stem = parts[-1].rsplit(".", maxsplit=1)[0]
    parts[-1] = f"{stem}.txt"
    return "/".join(parts)


def _issue(
    *,
    code: str,
    severity: Severity,
    message: str,
    relative_path: str,
    suggested_action: str,
    image_id: str | None = None,
    line_number: int | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    metrics: dict[str, object] | None = None,
) -> Issue:
    normalized_metrics = metrics or {}
    return Issue(
        issue_id=_stable_issue_id(code, relative_path, line_number, bbox),
        code=code,
        severity=severity,
        message=message,
        relative_path=relative_path,
        image_id=image_id,
        annotation_line=line_number,
        bbox=bbox,
        metrics=normalized_metrics,
        suggested_action=suggested_action,
        evidence={
            "path": relative_path,
            "line_number": line_number,
            "bbox": list(bbox) if bbox is not None else None,
            "metrics": normalized_metrics,
        },
    )


def _check_image_label(image: ImageRecord) -> Issue | None:
    if image.label_status == "missing":
        expected_path = _expected_label_path(image.relative_path)
        return _issue(
            code=LABEL_MISSING,
            severity=Severity.WARNING,
            message="Image has no matching label file; verify whether it is a negative sample.",
            relative_path=expected_path,
            image_id=image.image_id,
            metrics={"image_path": image.relative_path, "label_status": "missing"},
            suggested_action=(
                "Confirm the image is an intentional negative sample or add its label file."
            ),
        )
    if image.label_status == "empty" and image.label_path is not None:
        return _issue(
            code=LABEL_EMPTY,
            severity=Severity.INFO,
            message="Label file is empty; this may be an intentional negative sample.",
            relative_path=image.label_path,
            image_id=image.image_id,
            metrics={"image_path": image.relative_path, "label_status": "empty"},
            suggested_action=(
                "Keep it if this is a verified negative sample; otherwise add annotations."
            ),
        )
    return None


def _check_parse_error(error: ParseErrorRecord) -> Issue:
    mapping: dict[str, tuple[str, Severity, str]] = {
        "label.orphan": (
            LABEL_ORPHAN,
            Severity.WARNING,
            "Move or rename the label to match an image, or remove it after review.",
        ),
        "label.class_id_invalid": (
            CLASS_ID_INVALID,
            Severity.ERROR,
            "Replace the class token with a declared integer class ID.",
        ),
        "label.unknown_class": (
            CLASS_ID_INVALID,
            Severity.ERROR,
            "Map the class ID to an entry declared in data.yaml.",
        ),
        "label.bbox_non_positive": (
            BBOX_NON_POSITIVE,
            Severity.ERROR,
            "Correct or remove the box after reviewing the source image.",
        ),
        "label.bbox_out_of_range": (
            BBOX_OUT_OF_RANGE,
            Severity.ERROR,
            "Normalize center coordinates and size values to the [0, 1] range.",
        ),
        "label.bbox_crosses_border": (
            BBOX_CROSSES_BORDER,
            Severity.ERROR,
            "Adjust the center or size so the full box remains inside the image.",
        ),
    }
    code, severity, action = mapping.get(
        error.code,
        (
            LABEL_PARSE_ERROR,
            Severity.ERROR,
            "Correct the row to five finite numeric YOLO Detection fields.",
        ),
    )
    metrics: dict[str, object] = dict(error.metrics)
    if error.class_id is not None:
        metrics["class_id"] = error.class_id
    if error.raw_line is not None:
        metrics["raw_line"] = error.raw_line
    return _issue(
        code=code,
        severity=severity,
        message=error.message,
        relative_path=error.source_path,
        line_number=error.line_number,
        bbox=error.bbox,
        metrics=metrics,
        suggested_action=action,
    )


def _check_tiny_box(
    annotation: AnnotationRecord,
    image: ImageRecord,
    config: AnnotationCheckConfig,
) -> Issue | None:
    width_pixels = annotation.bbox.width * image.width
    height_pixels = annotation.bbox.height * image.height
    area_pixels = width_pixels * height_pixels
    if not (
        width_pixels < config.min_bbox_width_pixels
        or height_pixels < config.min_bbox_height_pixels
        or area_pixels < config.min_bbox_area_pixels
    ):
        return None
    bbox = annotation.bbox.root
    return _issue(
        code=BBOX_TINY,
        severity=Severity.WARNING,
        message="Bounding box is smaller than the configured pixel threshold.",
        relative_path=annotation.source_path,
        image_id=annotation.image_id,
        line_number=annotation.line_number,
        bbox=bbox,
        metrics={
            "width_pixels": width_pixels,
            "height_pixels": height_pixels,
            "area_pixels": area_pixels,
            "min_width_pixels": config.min_bbox_width_pixels,
            "min_height_pixels": config.min_bbox_height_pixels,
            "min_area_pixels": config.min_bbox_area_pixels,
        },
        suggested_action=(
            "Review the object at full resolution and enlarge or remove the box if needed."
        ),
    )


def check_annotations(
    manifest: DatasetManifest,
    *,
    config: AnnotationCheckConfig | None = None,
) -> list[Issue]:
    """Return deterministic annotation issues without reading or mutating files."""

    active_config = config or AnnotationCheckConfig()
    issues: list[Issue] = []
    seen_ids: set[str] = set()

    def add(issue: Issue | None) -> None:
        if issue is not None and issue.issue_id not in seen_ids:
            seen_ids.add(issue.issue_id)
            issues.append(issue)

    images_by_id = {image.image_id: image for image in manifest.images}
    for image in manifest.images:
        add(_check_image_label(image))
    for error in manifest.parse_errors:
        add(_check_parse_error(error))
    for annotation in manifest.annotations:
        image = images_by_id.get(annotation.image_id)
        if image is not None:
            add(_check_tiny_box(annotation, image, active_config))
    return issues
