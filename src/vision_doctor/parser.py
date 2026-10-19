"""YOLO Detection dataset discovery and tolerant label parsing."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, Literal
from urllib.parse import urlsplit

import yaml
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError

from vision_doctor.config import UploadLimits
from vision_doctor.models import (
    AnnotationRecord,
    BoundingBox,
    DatasetManifest,
    DatasetSummary,
    ImageRecord,
    ParseErrorRecord,
)


class DatasetParseError(ValueError):
    """Raised when a dataset-level structure cannot be parsed safely."""


@dataclass(frozen=True)
class _SplitDirectories:
    """Resolved, dataset-contained directories for one logical split."""

    name: str
    images: Path
    labels: Path | None


def _relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _load_class_names(data_yaml: Path) -> tuple[dict[int, str], dict[str, Any]]:
    try:
        document = yaml.safe_load(data_yaml.read_text(encoding="utf-8"))
    except UnicodeDecodeError as error:
        raise DatasetParseError("data.yaml must be valid UTF-8 text.") from error
    except yaml.YAMLError as error:
        raise DatasetParseError(f"data.yaml contains invalid YAML: {error}.") from error

    if not isinstance(document, dict):
        raise DatasetParseError("data.yaml must contain a YAML mapping at its root.")
    if "names" not in document:
        raise DatasetParseError("data.yaml is missing required field 'names'.")
    names = document["names"]
    if isinstance(names, list):
        if not names or any(not isinstance(name, str) or not name.strip() for name in names):
            raise DatasetParseError("data.yaml names list must contain non-empty strings.")
        class_names = {index: name.strip() for index, name in enumerate(names)}
    elif isinstance(names, dict):
        if not names:
            raise DatasetParseError("data.yaml names mapping must not be empty.")
        class_names = {}
        for class_id, name in names.items():
            if isinstance(class_id, bool) or not isinstance(class_id, int) or class_id < 0:
                raise DatasetParseError(
                    "data.yaml names mapping must use non-negative integer keys."
                )
            if not isinstance(name, str) or not name.strip():
                raise DatasetParseError(
                    "data.yaml names mapping values must be non-empty strings."
                )
            class_names[class_id] = name.strip()
        expected_ids = list(range(len(class_names)))
        if sorted(class_names) != expected_ids:
            raise DatasetParseError(
                "data.yaml names mapping keys must be contiguous starting at 0."
            )
    else:
        raise DatasetParseError(
            "data.yaml must define names as a list or integer-key mapping."
        )

    nc = document.get("nc")
    if nc is not None:
        if isinstance(nc, bool) or not isinstance(nc, int) or nc <= 0:
            raise DatasetParseError("data.yaml field 'nc' must be a positive integer.")
        if nc != len(class_names):
            raise DatasetParseError(
                f"data.yaml field 'nc' is {nc} but names defines "
                f"{len(class_names)} classes."
            )
    return class_names, document


def _discover_by_key(directory: Path, suffixes: frozenset[str]) -> dict[str, Path]:
    discovered: dict[str, Path] = {}
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        relative_key = path.relative_to(directory).with_suffix("").as_posix()
        lookup_key = relative_key.casefold()
        if lookup_key in discovered:
            raise DatasetParseError(
                f"Multiple files map to dataset key {relative_key!r}."
            )
        discovered[lookup_key] = path
    return discovered


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_image_record(
    image_path: Path,
    dataset_root: Path,
    annotation_count: int,
    label_path: str | None,
    label_status: Literal["missing", "empty", "present"],
) -> ImageRecord:
    try:
        with Image.open(image_path) as image:
            image.load()
            width, height = image.size
    except (OSError, UnidentifiedImageError) as error:
        relative_path = _relative_path(image_path, dataset_root)
        raise DatasetParseError(
            f"Image could not be decoded while building the manifest: {relative_path}."
        ) from error

    relative_path = _relative_path(image_path, dataset_root)
    return ImageRecord(
        image_id=relative_path,
        relative_path=relative_path,
        width=width,
        height=height,
        file_size_bytes=image_path.stat().st_size,
        annotation_count=annotation_count,
        label_path=label_path,
        label_status=label_status,
        sha256=_sha256(image_path),
    )


def _parse_label_file(
    label_path: Path,
    image_id: str,
    dataset_root: Path,
    class_names: dict[int, str],
) -> tuple[
    list[AnnotationRecord],
    list[ParseErrorRecord],
    Literal["empty", "present"],
]:
    relative_label_path = _relative_path(label_path, dataset_root)
    try:
        lines = label_path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return (
            [],
            [
                ParseErrorRecord(
                    code="label.invalid_encoding",
                    message="Label file must be valid UTF-8 text.",
                    source_path=relative_label_path,
                )
            ],
            "present",
        )

    annotations: list[AnnotationRecord] = []
    errors: list[ParseErrorRecord] = []
    has_content = False
    for line_number, raw_line in enumerate(lines, start=1):
        stripped_line = raw_line.strip()
        if not stripped_line:
            continue
        has_content = True
        fields = stripped_line.split()
        if len(fields) != 5:
            errors.append(
                ParseErrorRecord(
                    code="label.invalid_field_count",
                    message="YOLO Detection rows require exactly five fields.",
                    source_path=relative_label_path,
                    line_number=line_number,
                    raw_line=raw_line,
                    metrics={"field_count": len(fields)},
                )
            )
            continue
        try:
            class_id = int(fields[0])
        except ValueError:
            errors.append(
                ParseErrorRecord(
                    code="label.class_id_invalid",
                    message="Class ID must be an integer.",
                    source_path=relative_label_path,
                    line_number=line_number,
                    raw_line=raw_line,
                    metrics={"class_id_token": fields[0]},
                )
            )
            continue
        try:
            coordinates = tuple(float(value) for value in fields[1:])
        except ValueError:
            errors.append(
                ParseErrorRecord(
                    code="label.non_numeric",
                    message="Bounding-box values must be numeric.",
                    source_path=relative_label_path,
                    line_number=line_number,
                    raw_line=raw_line,
                    class_id=class_id,
                    metrics={"bbox_tokens": fields[1:]},
                )
            )
            continue
        if not all(math.isfinite(value) for value in coordinates):
            errors.append(
                ParseErrorRecord(
                    code="label.non_finite",
                    message="Bounding-box values must not be NaN or infinite.",
                    source_path=relative_label_path,
                    line_number=line_number,
                    raw_line=raw_line,
                    class_id=class_id,
                    metrics={"bbox_tokens": fields[1:]},
                )
            )
            continue
        if class_id not in class_names:
            errors.append(
                ParseErrorRecord(
                    code="label.unknown_class",
                    message=f"Class ID {class_id} is not declared in data.yaml.",
                    source_path=relative_label_path,
                    line_number=line_number,
                    raw_line=raw_line,
                    class_id=class_id,
                    bbox=coordinates,
                    metrics={"declared_class_count": len(class_names)},
                )
            )
            continue
        x_center, y_center, width, height = coordinates
        if width <= 0.0 or height <= 0.0:
            errors.append(
                ParseErrorRecord(
                    code="label.bbox_non_positive",
                    message="Bounding-box width and height must be positive.",
                    source_path=relative_label_path,
                    line_number=line_number,
                    raw_line=raw_line,
                    class_id=class_id,
                    bbox=coordinates,
                    metrics={"width": width, "height": height},
                )
            )
            continue
        if not (
            0.0 <= x_center <= 1.0
            and 0.0 <= y_center <= 1.0
            and width <= 1.0
            and height <= 1.0
        ):
            errors.append(
                ParseErrorRecord(
                    code="label.bbox_out_of_range",
                    message="YOLO center and size values must be normalized to [0, 1].",
                    source_path=relative_label_path,
                    line_number=line_number,
                    raw_line=raw_line,
                    class_id=class_id,
                    bbox=coordinates,
                    metrics={
                        "x_center": x_center,
                        "y_center": y_center,
                        "width": width,
                        "height": height,
                    },
                )
            )
            continue
        left = x_center - width / 2
        top = y_center - height / 2
        right = x_center + width / 2
        bottom = y_center + height / 2
        if left < 0.0 or top < 0.0 or right > 1.0 or bottom > 1.0:
            errors.append(
                ParseErrorRecord(
                    code="label.bbox_crosses_border",
                    message="Bounding box crosses the normalized image border.",
                    source_path=relative_label_path,
                    line_number=line_number,
                    raw_line=raw_line,
                    class_id=class_id,
                    bbox=coordinates,
                    metrics={
                        "left": left,
                        "top": top,
                        "right": right,
                        "bottom": bottom,
                    },
                )
            )
            continue
        try:
            bbox = BoundingBox.model_validate(coordinates)
            annotation = AnnotationRecord(
                image_id=image_id,
                class_id=class_id,
                bbox=bbox,
                source_path=relative_label_path,
                line_number=line_number,
            )
        except ValidationError as error:
            errors.append(
                ParseErrorRecord(
                    code="label.invalid_bbox",
                    message=f"Bounding box is invalid: {error.errors()[0]['msg']}.",
                    source_path=relative_label_path,
                    line_number=line_number,
                    raw_line=raw_line,
                    class_id=class_id,
                    bbox=coordinates,
                )
            )
            continue
        annotations.append(annotation)
    return annotations, errors, "present" if has_content else "empty"


def resolve_yolo_dataset_root(dataset_root: str | Path) -> Path:
    """Locate the one dataset root represented by ``data.yaml``.

    ZIP archives commonly contain either the dataset files directly or one
    enclosing directory such as ``dataset/``. Unrelated root files are allowed,
    but multiple candidate datasets are rejected instead of being guessed.
    """

    root = Path(dataset_root).resolve()
    if not root.is_dir():
        raise DatasetParseError("Dataset root does not exist or is not a directory.")
    candidates = sorted(
        path
        for path in root.rglob("data.yaml")
        if path.is_file()
        and "__macosx" not in {
            part.casefold() for part in path.relative_to(root).parts
        }
    )
    if not candidates:
        raise DatasetParseError(
            "Dataset archive must contain data.yaml exactly once at its dataset root."
        )
    if len(candidates) > 1:
        relative_candidates = ", ".join(
            path.relative_to(root).as_posix() for path in candidates
        )
        raise DatasetParseError(
            "Dataset archive contains multiple data.yaml files; dataset root is "
            f"ambiguous: {relative_candidates}."
        )
    return candidates[0].parent.resolve()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _resolve_yaml_directory(
    root: Path,
    base: Path,
    field: str,
    value: object,
) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise DatasetParseError(
            f"data.yaml field {field!r} must be a non-empty relative directory path."
        )
    raw_value = value.strip()
    parsed = urlsplit(raw_value)
    windows_path = PureWindowsPath(raw_value)
    if (
        parsed.scheme
        or raw_value.startswith(("/", "\\", "//"))
        or windows_path.is_absolute()
        or bool(windows_path.drive)
    ):
        raise DatasetParseError(
            f"data.yaml field {field!r} must use a safe relative local path."
        )
    normalized = raw_value.replace("\\", "/")
    resolved = (base / Path(normalized)).resolve()
    if not _is_within(resolved, root):
        raise DatasetParseError(
            f"Configured path for data.yaml field {field!r} points outside the "
            "extracted dataset root and was rejected."
        )
    if not resolved.is_dir():
        raise DatasetParseError(
            f"Configured directory for data.yaml field {field!r} does not exist: "
            f"{normalized}."
        )
    return resolved


def _split_from_image_directory(
    root: Path,
    split: str,
    configured_directory: Path,
) -> _SplitDirectories:
    images_directory = configured_directory
    if (configured_directory / "images").is_dir():
        images_directory = configured_directory / "images"

    relative_parts = list(images_directory.relative_to(root).parts)
    image_markers = [
        index for index, part in enumerate(relative_parts) if part.casefold() == "images"
    ]
    labels_directory: Path | None = None
    if image_markers:
        label_parts = list(relative_parts)
        label_parts[image_markers[-1]] = "labels"
        candidate = root.joinpath(*label_parts)
        if candidate.is_dir():
            labels_directory = candidate
    return _SplitDirectories(split, images_directory, labels_directory)


def _autodetected_layouts(root: Path) -> list[list[_SplitDirectories]]:
    layouts: list[list[_SplitDirectories]] = []

    split_first_train = root / "train" / "images"
    if split_first_train.is_dir():
        split_first: list[_SplitDirectories] = []
        for split in ("train", "val", "test"):
            images = root / split / "images"
            if images.is_dir():
                labels = root / split / "labels"
                split_first.append(
                    _SplitDirectories(split, images, labels if labels.is_dir() else None)
                )
        layouts.append(split_first)

    images_first_train = root / "images" / "train"
    if images_first_train.is_dir():
        images_first: list[_SplitDirectories] = []
        for split in ("train", "val", "test"):
            images = root / "images" / split
            if images.is_dir():
                labels = root / "labels" / split
                images_first.append(
                    _SplitDirectories(split, images, labels if labels.is_dir() else None)
                )
        layouts.append(images_first)

    flat_images = root / "images"
    has_named_image_splits = any(
        (flat_images / split).is_dir() for split in ("train", "val", "test")
    )
    if flat_images.is_dir() and not has_named_image_splits:
        flat_labels = root / "labels"
        layouts.append(
            [
                _SplitDirectories(
                    "all",
                    flat_images,
                    flat_labels if flat_labels.is_dir() else None,
                )
            ]
        )
    return layouts


def _resolve_split_directories(
    root: Path,
    document: dict[str, Any],
) -> list[_SplitDirectories]:
    base = root
    if "path" in document:
        base = _resolve_yaml_directory(root, root, "path", document["path"])

    configured: list[_SplitDirectories] = []
    for split in ("train", "val", "test"):
        if split not in document:
            continue
        directory = _resolve_yaml_directory(root, base, split, document[split])
        configured.append(_split_from_image_directory(root, split, directory))

    if configured:
        if not any(item.name == "train" for item in configured):
            layouts = _autodetected_layouts(base)
            if len(layouts) == 1:
                train = next(
                    (item for item in layouts[0] if item.name == "train"), None
                )
                if train is not None:
                    configured.insert(0, train)
            if not any(item.name == "train" for item in configured):
                raise DatasetParseError(
                    "data.yaml is missing field 'train' and no unique train image "
                    "directory could be detected."
                )
        resolved_directories = [item.images.resolve() for item in configured]
        if len(set(resolved_directories)) != len(resolved_directories):
            raise DatasetParseError(
                "data.yaml maps multiple splits to the same image directory."
            )
        return configured

    layouts = _autodetected_layouts(base)
    if not layouts:
        raise DatasetParseError(
            "No supported YOLO layout could be determined. Checked split-first, "
            "images-first, and flat layouts."
        )
    if len(layouts) > 1:
        raise DatasetParseError(
            "Multiple supported YOLO layouts were found; dataset structure is "
            "ambiguous. Configure explicit train/val/test paths in data.yaml."
        )
    return layouts[0]


def parse_yolo_dataset(
    dataset_root: str | Path,
    *,
    source_archive: str | None = None,
    upload_limits: UploadLimits | None = None,
) -> DatasetManifest:
    """Parse a safe, unambiguous YOLO Detection layout into a manifest."""

    root = resolve_yolo_dataset_root(dataset_root)
    data_yaml = root / "data.yaml"
    class_names, yaml_document = _load_class_names(data_yaml)
    active_limits = upload_limits or UploadLimits()
    split_directories = _resolve_split_directories(root, yaml_document)

    image_paths: dict[str, Path] = {}
    label_paths: dict[str, Path] = {}
    for split in split_directories:
        split_images = _discover_by_key(
            split.images,
            active_limits.allowed_image_extensions,
        )
        if not split_images:
            if split.name in {"val", "test"}:
                continue
            relative_directory = _relative_path(split.images, root)
            raise DatasetParseError(
                f"No supported images were found in the resolved {split.name} "
                f"directory {relative_directory!r}."
            )
        split_labels = (
            _discover_by_key(split.labels, frozenset({".txt"}))
            if split.labels is not None
            else {}
        )
        image_paths.update(
            {f"{split.name}/{key}": path for key, path in split_images.items()}
        )
        label_paths.update(
            {f"{split.name}/{key}": path for key, path in split_labels.items()}
        )
    if not image_paths:
        raise DatasetParseError("Dataset contains no supported images.")

    annotations: list[AnnotationRecord] = []
    parse_errors: list[ParseErrorRecord] = []
    images: list[ImageRecord] = []
    unreadable_image_paths: list[str] = []

    for image_key, image_path in image_paths.items():
        relative_image_path = _relative_path(image_path, root)
        image_annotations: list[AnnotationRecord] = []
        label_path = label_paths.get(image_key)
        relative_label_path: str | None = None
        label_status: Literal["missing", "empty", "present"] = "missing"
        if label_path is not None:
            relative_label_path = _relative_path(label_path, root)
            image_annotations, label_errors, label_status = _parse_label_file(
                label_path,
                relative_image_path,
                root,
                class_names,
            )
            parse_errors.extend(label_errors)
        annotations.extend(image_annotations)
        try:
            image_record = _read_image_record(
                image_path,
                root,
                len(image_annotations),
                relative_label_path,
                label_status,
            )
        except DatasetParseError:
            unreadable_image_paths.append(relative_image_path)
            continue
        images.append(image_record)

    for label_key, label_path in label_paths.items():
        if label_key not in image_paths:
            parse_errors.append(
                ParseErrorRecord(
                    code="label.orphan",
                    message="Label file has no matching supported image.",
                    source_path=_relative_path(label_path, root),
                )
            )

    dataset_name_value = yaml_document.get("name", root.name)
    if not isinstance(dataset_name_value, str) or not dataset_name_value.strip():
        raise DatasetParseError("Optional data.yaml name must be a non-empty string.")

    summary = DatasetSummary(
        image_count=len(image_paths),
        label_file_count=len(label_paths),
        annotation_count=len(annotations),
        class_count=len(class_names),
        issue_count=len(parse_errors),
        total_size_bytes=sum(path.stat().st_size for path in image_paths.values()),
    )
    return DatasetManifest(
        dataset_name=dataset_name_value.strip(),
        source_archive=source_archive or root.name,
        images=images,
        annotations=annotations,
        class_names=class_names,
        parse_errors=parse_errors,
        unreadable_image_paths=unreadable_image_paths,
        summary=summary,
    )
