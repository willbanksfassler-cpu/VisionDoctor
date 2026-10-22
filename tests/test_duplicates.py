"""Tests for exact and perceptual duplicate grouping."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
from PIL import Image

from vision_doctor.checkers.duplicates import (
    check_split_leakage,
    find_duplicate_groups,
)
from vision_doctor.config import DuplicateDetectionConfig
from vision_doctor.models import Severity
from vision_doctor.parser import parse_yolo_dataset


def _write_dataset(root: Path) -> None:
    (root / "train" / "images").mkdir(parents=True)
    (root / "train" / "labels").mkdir(parents=True)
    (root / "val" / "images").mkdir(parents=True)
    (root / "val" / "labels").mkdir(parents=True)
    (root / "data.yaml").write_text("names: [object]\n", encoding="utf-8")
    random = np.random.default_rng(42)
    base = random.integers(0, 256, size=(128, 128, 3), dtype=np.uint8)
    Image.fromarray(base).save(root / "train/images/a.png")
    shutil.copyfile(root / "train/images/a.png", root / "train/images/b.png")
    near = base.copy()
    near[0, 0, 0] = (int(near[0, 0, 0]) + 1) % 256
    Image.fromarray(near).save(root / "train/images/c.png")
    unrelated = np.random.default_rng(7).integers(
        0, 256, size=(128, 128, 3), dtype=np.uint8
    )
    Image.fromarray(unrelated).save(root / "val/images/d.png")


def test_exact_and_near_duplicates_are_distinct_and_deterministic(
    tmp_path: Path,
) -> None:
    _write_dataset(tmp_path)
    manifest = parse_yolo_dataset(tmp_path)

    groups = find_duplicate_groups(manifest, tmp_path)
    exact = [group for group in groups if group.kind == "exact"]
    near = [group for group in groups if group.kind == "near"]

    assert len(exact) == 1
    assert exact[0].image_ids == ["train/images/a.png", "train/images/b.png"]
    assert exact[0].representative_image_id == "train/images/a.png"
    assert exact[0].hamming_distance == 0
    assert len(near) == 1
    assert near[0].image_ids == ["train/images/a.png", "train/images/c.png"]
    assert near[0].representative_image_id == "train/images/a.png"
    assert near[0].hamming_distance <= 4
    assert "val/images/d.png" not in exact[0].image_ids + near[0].image_ids
    assert len(near[0].pair_distances) == 1
    assert groups == find_duplicate_groups(manifest, tmp_path)
    assert check_split_leakage(groups) == []


def test_pairwise_limit_is_explicit(tmp_path: Path) -> None:
    _write_dataset(tmp_path)
    manifest = parse_yolo_dataset(tmp_path)

    config = DuplicateDetectionConfig(max_images_for_pairwise=3)

    try:
        find_duplicate_groups(manifest, tmp_path, config=config)
    except ValueError as error:
        assert "at most 3 images" in str(error)
    else:
        raise AssertionError("Expected configured pairwise size limit to be enforced")


def test_cross_split_exact_and_near_groups_emit_one_stable_issue_each(
    tmp_path: Path,
) -> None:
    _write_dataset(tmp_path)
    (tmp_path / "test/images").mkdir(parents=True)
    (tmp_path / "test/labels").mkdir(parents=True)
    shutil.move(tmp_path / "train/images/b.png", tmp_path / "val/images/b.png")
    shutil.move(tmp_path / "train/images/c.png", tmp_path / "test/images/c.png")
    manifest = parse_yolo_dataset(tmp_path)

    groups = find_duplicate_groups(manifest, tmp_path)
    first = check_split_leakage(groups)
    second = check_split_leakage(groups)
    by_code = {issue.code: issue for issue in first}

    assert set(by_code) == {"SPLIT_LEAKAGE_EXACT", "SPLIT_LEAKAGE_NEAR"}
    assert by_code["SPLIT_LEAKAGE_EXACT"].severity is Severity.ERROR
    assert by_code["SPLIT_LEAKAGE_NEAR"].severity is Severity.WARNING
    assert "potential leakage candidate" in (
        by_code["SPLIT_LEAKAGE_NEAR"].message
    )
    assert by_code["SPLIT_LEAKAGE_EXACT"].metrics["splits"] == ["train", "val"]
    assert by_code["SPLIT_LEAKAGE_NEAR"].metrics["splits"] == ["test", "train"]
    assert all(issue.metrics["image_count"] == 2 for issue in first)
    assert all(issue.relative_path.startswith("train/") for issue in first)
    assert [issue.issue_id for issue in first] == [
        issue.issue_id for issue in second
    ]
