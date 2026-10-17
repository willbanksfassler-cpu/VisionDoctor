"""Tests for supported YOLO Detection layouts and tolerant label parsing."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from vision_doctor.parser import DatasetParseError, parse_yolo_dataset


def write_image(path: Path, *, size: tuple[int, int] = (32, 24)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color=(20, 40, 60)).save(path)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_flat_layout_and_names_list_are_parsed(tmp_path: Path) -> None:
    write_text(tmp_path / "data.yaml", "name: flat\nnames: [cat, dog]\n")
    write_image(tmp_path / "images" / "sample.JPG")
    write_text(tmp_path / "labels" / "sample.txt", "1 0.5 0.5 0.4 0.2\n")

    manifest = parse_yolo_dataset(tmp_path, source_archive="flat.zip")

    assert manifest.dataset_name == "flat"
    assert manifest.source_archive == "flat.zip"
    assert manifest.class_names == {0: "cat", 1: "dog"}
    assert manifest.images[0].relative_path == "images/sample.JPG"
    assert manifest.images[0].annotation_count == 1
    assert manifest.images[0].label_path == "labels/sample.txt"
    assert manifest.images[0].label_status == "present"
    assert manifest.annotations[0].source_path == "labels/sample.txt"
    assert manifest.annotations[0].class_id == 1
    assert manifest.parse_errors == []
    assert manifest.summary.annotation_count == 1


def test_split_layout_and_integer_names_mapping_are_parsed(tmp_path: Path) -> None:
    write_text(tmp_path / "data.yaml", "names:\n  0: cat\n  1: dog\n")
    write_image(tmp_path / "images" / "train" / "a.png")
    write_image(tmp_path / "images" / "val" / "b.webp")
    write_text(tmp_path / "labels" / "train" / "a.txt", "0 0.5 0.5 0.2 0.2\n")
    write_text(tmp_path / "labels" / "val" / "b.txt", "1 0.5 0.5 0.4 0.4\n")

    manifest = parse_yolo_dataset(tmp_path)

    assert [image.relative_path for image in manifest.images] == [
        "images/train/a.png",
        "images/val/b.webp",
    ]
    assert [annotation.source_path for annotation in manifest.annotations] == [
        "labels/train/a.txt",
        "labels/val/b.txt",
    ]
    assert manifest.summary.image_count == 2
    assert manifest.summary.label_file_count == 2


def test_bad_label_rows_are_recorded_and_valid_rows_continue(tmp_path: Path) -> None:
    write_text(tmp_path / "data.yaml", "names: [cat]\n")
    write_image(tmp_path / "images" / "sample.bmp")
    write_text(
        tmp_path / "labels" / "sample.txt",
        "0 0.5 0.5 0.2 0.2\n"
        "0 0.5 0.5 0.2\n"
        "cat 0.5 0.5 0.2 0.2\n"
        "4 0.5 0.5 0.2 0.2\n"
        "0 1.2 0.5 0.2 0.2",
    )

    manifest = parse_yolo_dataset(tmp_path)

    assert len(manifest.annotations) == 1
    assert [error.code for error in manifest.parse_errors] == [
        "label.invalid_field_count",
        "label.class_id_invalid",
        "label.unknown_class",
        "label.bbox_out_of_range",
    ]
    assert all(error.source_path == "labels/sample.txt" for error in manifest.parse_errors)
    assert manifest.summary.issue_count == 4


def test_orphan_label_is_recorded(tmp_path: Path) -> None:
    write_text(tmp_path / "data.yaml", "names: [cat]\n")
    write_image(tmp_path / "images" / "sample.jpeg")
    write_text(tmp_path / "labels" / "orphan.txt", "0 0.5 0.5 0.2 0.2\n")

    manifest = parse_yolo_dataset(tmp_path)

    assert manifest.images[0].annotation_count == 0
    assert [error.code for error in manifest.parse_errors] == ["label.orphan"]


def test_missing_and_empty_label_state_is_preserved(tmp_path: Path) -> None:
    write_text(tmp_path / "data.yaml", "names: [cat]\n")
    write_image(tmp_path / "images" / "missing.jpg")
    write_image(tmp_path / "images" / "empty.png")
    write_text(tmp_path / "labels" / "empty.txt", "\n  \n")

    manifest = parse_yolo_dataset(tmp_path)
    images = {image.relative_path: image for image in manifest.images}

    assert images["images/missing.jpg"].label_status == "missing"
    assert images["images/missing.jpg"].label_path is None
    assert images["images/empty.png"].label_status == "empty"
    assert images["images/empty.png"].label_path == "labels/empty.txt"


def test_bbox_error_categories_are_preserved(tmp_path: Path) -> None:
    write_text(tmp_path / "data.yaml", "names: [cat]\n")
    write_image(tmp_path / "images" / "sample.png")
    write_text(
        tmp_path / "labels" / "sample.txt",
        "0 0.5 0.5 0 0.2\n"
        "0 1.2 0.5 0.2 0.2\n"
        "0 0.05 0.5 0.2 0.2\n"
        "0 nope 0.5 0.2 0.2\n"
        "0 NaN 0.5 0.2 0.2\n"
        "0 Inf 0.5 0.2 0.2",
    )

    manifest = parse_yolo_dataset(tmp_path)

    assert [error.code for error in manifest.parse_errors] == [
        "label.bbox_non_positive",
        "label.bbox_out_of_range",
        "label.bbox_crosses_border",
        "label.non_numeric",
        "label.non_finite",
        "label.non_finite",
    ]


def test_unreadable_image_is_preserved_without_stopping_dataset(tmp_path: Path) -> None:
    write_text(tmp_path / "data.yaml", "names: [cat]\n")
    damaged = tmp_path / "images" / "damaged.png"
    damaged.parent.mkdir(parents=True)
    damaged.write_bytes(b"not an image")
    write_image(tmp_path / "images" / "valid.png")
    write_text(tmp_path / "labels" / "damaged.txt", "0 0.5 0.5 0.2 0.2\n")
    write_text(tmp_path / "labels" / "valid.txt", "0 0.5 0.5 0.2 0.2\n")

    manifest = parse_yolo_dataset(tmp_path)

    assert manifest.unreadable_image_paths == ["images/damaged.png"]
    assert [image.relative_path for image in manifest.images] == ["images/valid.png"]
    assert manifest.summary.image_count == 2
    assert manifest.summary.annotation_count == 2
    assert manifest.summary.total_size_bytes == sum(
        path.stat().st_size for path in (damaged, tmp_path / "images" / "valid.png")
    )


@pytest.mark.parametrize(
    ("yaml_content", "message"),
    [
        ("names: animal\n", "list or integer-key mapping"),
        ("names:\n  cat: 0\n", "non-negative integer keys"),
        ("names:\n  1: dog\n", "contiguous starting at 0"),
        ("- names\n- cat\n", "mapping at its root"),
    ],
)
def test_unsupported_data_yaml_is_rejected(
    tmp_path: Path, yaml_content: str, message: str
) -> None:
    write_text(tmp_path / "data.yaml", yaml_content)
    (tmp_path / "images").mkdir()
    (tmp_path / "labels").mkdir()

    with pytest.raises(DatasetParseError, match=message):
        parse_yolo_dataset(tmp_path)


def test_missing_or_invalid_data_yaml_has_clear_error(tmp_path: Path) -> None:
    with pytest.raises(DatasetParseError, match="contain data.yaml"):
        parse_yolo_dataset(tmp_path)

    write_text(tmp_path / "data.yaml", "names: [cat\n")
    with pytest.raises(DatasetParseError, match="invalid YAML"):
        parse_yolo_dataset(tmp_path)
