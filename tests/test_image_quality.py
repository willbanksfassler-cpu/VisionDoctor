"""Tests for explainable image-quality measurements and failure isolation."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from vision_doctor.checkers.image_quality import (
    IMAGE_BLURRY,
    IMAGE_BRIGHT,
    IMAGE_DARK,
    IMAGE_LOW_RESOLUTION,
    IMAGE_UNREADABLE,
    check_image_quality,
)
from vision_doctor.config import ImageQualityThresholds
from vision_doctor.models import DatasetManifest, DatasetSummary, ImageRecord
from vision_doctor.parser import parse_yolo_dataset


def _save(path: Path, pixels: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(pixels.astype(np.uint8), mode="RGB").save(path)


def _record(path: str, width: int, height: int) -> ImageRecord:
    return ImageRecord(
        image_id=path,
        relative_path=path,
        width=width,
        height=height,
        file_size_bytes=1,
    )


def _manifest(images: list[ImageRecord]) -> DatasetManifest:
    return DatasetManifest(
        dataset_name="quality",
        source_archive="quality.zip",
        images=images,
        class_names={0: "object"},
        summary=DatasetSummary(
            image_count=len(images),
            label_file_count=0,
            annotation_count=0,
            class_count=1,
        ),
    )


def test_quality_cases_include_measurements_and_thresholds(tmp_path: Path) -> None:
    grid = np.indices((400, 400)).sum(axis=0) % 2
    normal = np.repeat((grid * 255)[:, :, None], 3, axis=2)
    _save(tmp_path / "images/normal.png", normal)
    _save(tmp_path / "images/blurry.png", np.full((400, 400, 3), 128))
    _save(tmp_path / "images/dark.png", np.full((400, 400, 3), 20))
    _save(tmp_path / "images/bright.png", np.full((400, 400, 3), 240))
    _save(tmp_path / "images/small.png", normal[:200, :200])
    damaged = tmp_path / "images/damaged.png"
    damaged.write_bytes(b"not an image")
    manifest = _manifest(
        [
            _record("images/normal.png", 400, 400),
            _record("images/blurry.png", 400, 400),
            _record("images/dark.png", 400, 400),
            _record("images/bright.png", 400, 400),
            _record("images/small.png", 200, 200),
            _record("images/damaged.png", 1, 1),
        ]
    )

    issues = check_image_quality(manifest, tmp_path)
    by_path: dict[str, set[str]] = {}
    for issue in issues:
        by_path.setdefault(issue.relative_path or "", set()).add(issue.code)

    assert "images/normal.png" not in by_path
    assert IMAGE_BLURRY in by_path["images/blurry.png"]
    assert IMAGE_DARK in by_path["images/dark.png"]
    assert IMAGE_BRIGHT in by_path["images/bright.png"]
    assert IMAGE_LOW_RESOLUTION in by_path["images/small.png"]
    assert by_path["images/damaged.png"] == {IMAGE_UNREADABLE}
    for issue in issues:
        assert issue.metrics
        assert {
            "measured_value",
            "fixed_threshold",
            "adaptive_threshold",
            "effective_threshold",
            "threshold_source",
            "sample_count",
        } <= set(issue.metrics)
        if issue.code != IMAGE_UNREADABLE:
            assert "grayscale_mean" in issue.metrics
            assert "laplacian_variance" in issue.metrics


def test_unreadable_image_does_not_stop_later_images(tmp_path: Path) -> None:
    damaged = tmp_path / "train/images/first.png"
    damaged.parent.mkdir(parents=True)
    damaged.write_bytes(b"broken")
    bright = np.full((400, 400, 3), 250)
    _save(tmp_path / "train/images/second.png", bright)
    (tmp_path / "train/labels").mkdir()
    (tmp_path / "val/images").mkdir(parents=True)
    (tmp_path / "val/labels").mkdir(parents=True)
    (tmp_path / "data.yaml").write_text("names: [object]\n", encoding="utf-8")

    manifest = parse_yolo_dataset(tmp_path)
    issues = check_image_quality(manifest, tmp_path)

    assert {issue.code for issue in issues} >= {IMAGE_UNREADABLE, IMAGE_BRIGHT}
    assert manifest.unreadable_image_paths == ["train/images/first.png"]
    assert manifest.summary.image_count == 2


def test_adaptive_mode_uses_split_statistics_and_ignores_damaged_images(
    tmp_path: Path,
) -> None:
    records: list[ImageRecord] = []
    for index, brightness in enumerate([*range(100, 112), 20]):
        relative = f"train/images/{index:02d}.png"
        _save(tmp_path / relative, np.full((400, 400, 3), brightness))
        records.append(_record(relative, 400, 400))
    damaged_path = "train/images/damaged.png"
    (tmp_path / damaged_path).write_bytes(b"damaged")
    records.append(_record(damaged_path, 1, 1))
    config = ImageQualityThresholds(mode="adaptive", adaptive_min_samples=12)

    issues = check_image_quality(_manifest(records), tmp_path, config=config)
    dark_issue = next(
        issue
        for issue in issues
        if issue.code == IMAGE_DARK and issue.relative_path.endswith("12.png")
    )
    unreadable = next(issue for issue in issues if issue.code == IMAGE_UNREADABLE)

    assert dark_issue.metrics["threshold_source"] == "adaptive_mad"
    assert dark_issue.metrics["sample_count"] == 13
    assert dark_issue.metrics["fixed_threshold"] == 45.0
    assert dark_issue.metrics["adaptive_threshold"] == 80.0
    assert dark_issue.metrics["effective_threshold"] == 80.0
    assert dark_issue.metrics["measured_value"] == pytest.approx(20.0)
    assert unreadable.metrics["sample_count"] == 13


def test_adaptive_mode_falls_back_to_fixed_for_small_split(tmp_path: Path) -> None:
    records: list[ImageRecord] = []
    for index, brightness in enumerate((20, 128)):
        relative = f"val/images/{index}.png"
        _save(tmp_path / relative, np.full((400, 400, 3), brightness))
        records.append(_record(relative, 400, 400))
    config = ImageQualityThresholds(mode="adaptive", adaptive_min_samples=5)

    issues = check_image_quality(_manifest(records), tmp_path, config=config)
    dark_issue = next(issue for issue in issues if issue.code == IMAGE_DARK)

    assert dark_issue.metrics["threshold_source"] == (
        "fixed_fallback_insufficient_samples"
    )
    assert dark_issue.metrics["adaptive_threshold"] is None
    assert dark_issue.metrics["effective_threshold"] == 45.0
    assert dark_issue.metrics["sample_count"] == 2
