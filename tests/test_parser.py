"""Tests for split-first YOLO Detection discovery and tolerant label parsing."""

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


def prepare_dataset(
    root: Path,
    yaml_content: str = "names: [cat]\n",
    *,
    optional_splits: tuple[str, ...] = (),
) -> None:
    write_text(root / "data.yaml", yaml_content)
    for split in ("train", *optional_splits):
        (root / split / "images").mkdir(parents=True)
        (root / split / "labels").mkdir(parents=True)


def test_split_first_layout_and_names_list_are_parsed(tmp_path: Path) -> None:
    prepare_dataset(tmp_path, "name: canonical\nnames: [cat, dog]\n")
    write_image(tmp_path / "train" / "images" / "sample.JPG")
    write_text(
        tmp_path / "train" / "labels" / "sample.txt",
        "1 0.5 0.5 0.4 0.2\n",
    )

    manifest = parse_yolo_dataset(tmp_path, source_archive="canonical.zip")

    assert manifest.dataset_name == "canonical"
    assert manifest.source_archive == "canonical.zip"
    assert manifest.class_names == {0: "cat", 1: "dog"}
    assert manifest.images[0].relative_path == "train/images/sample.JPG"
    assert manifest.images[0].annotation_count == 1
    assert manifest.images[0].label_path == "train/labels/sample.txt"
    assert manifest.annotations[0].source_path == "train/labels/sample.txt"
    assert manifest.annotations[0].class_id == 1
    assert manifest.parse_errors == []


def test_wrapper_root_extras_test_split_and_names_mapping_are_supported(
    tmp_path: Path,
) -> None:
    dataset = tmp_path / "dataset"
    prepare_dataset(
        dataset,
        "names:\n  0: cat\n  1: dog\n",
        optional_splits=("val", "test"),
    )
    write_text(tmp_path / "packaging-note.md", "ignored\n")
    write_text(dataset / "LICENSE.txt", "ignored\n")
    write_image(dataset / "train" / "images" / "nested" / "a.png")
    write_image(dataset / "val" / "images" / "b.webp")
    write_image(dataset / "test" / "images" / "c.jpeg")
    write_text(
        dataset / "train" / "labels" / "nested" / "a.txt",
        "0 0.5 0.5 0.2 0.2\n",
    )
    write_text(dataset / "val" / "labels" / "b.txt", "1 0.5 0.5 0.4 0.4\n")
    write_text(dataset / "test" / "labels" / "c.txt", "0 0.5 0.5 0.3 0.3\n")

    manifest = parse_yolo_dataset(tmp_path)

    assert [image.relative_path for image in manifest.images] == [
        "train/images/nested/a.png",
        "val/images/b.webp",
        "test/images/c.jpeg",
    ]
    assert [annotation.source_path for annotation in manifest.annotations] == [
        "train/labels/nested/a.txt",
        "val/labels/b.txt",
        "test/labels/c.txt",
    ]
    assert manifest.summary.image_count == 3
    assert manifest.summary.label_file_count == 3


def test_bad_label_rows_are_recorded_and_valid_rows_continue(tmp_path: Path) -> None:
    prepare_dataset(tmp_path)
    write_image(tmp_path / "train" / "images" / "sample.bmp")
    write_text(
        tmp_path / "train" / "labels" / "sample.txt",
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
    assert all(
        error.source_path == "train/labels/sample.txt"
        for error in manifest.parse_errors
    )


def test_orphan_label_is_recorded(tmp_path: Path) -> None:
    prepare_dataset(tmp_path)
    write_image(tmp_path / "train" / "images" / "sample.jpeg")
    write_text(
        tmp_path / "train" / "labels" / "orphan.txt",
        "0 0.5 0.5 0.2 0.2\n",
    )

    manifest = parse_yolo_dataset(tmp_path)

    assert manifest.images[0].annotation_count == 0
    assert [error.code for error in manifest.parse_errors] == ["label.orphan"]


def test_missing_and_empty_label_state_is_preserved(tmp_path: Path) -> None:
    prepare_dataset(tmp_path, optional_splits=("val",))
    write_image(tmp_path / "train" / "images" / "missing.jpg")
    write_image(tmp_path / "val" / "images" / "empty.png")
    write_text(tmp_path / "val" / "labels" / "empty.txt", "\n  \n")

    manifest = parse_yolo_dataset(tmp_path)
    images = {image.relative_path: image for image in manifest.images}

    assert images["train/images/missing.jpg"].label_status == "missing"
    assert images["train/images/missing.jpg"].label_path is None
    assert images["val/images/empty.png"].label_status == "empty"
    assert images["val/images/empty.png"].label_path == "val/labels/empty.txt"


def test_bbox_error_categories_are_preserved(tmp_path: Path) -> None:
    prepare_dataset(tmp_path)
    write_image(tmp_path / "train" / "images" / "sample.png")
    write_text(
        tmp_path / "train" / "labels" / "sample.txt",
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
    prepare_dataset(tmp_path, optional_splits=("val",))
    damaged = tmp_path / "train" / "images" / "damaged.png"
    damaged.write_bytes(b"not an image")
    valid = tmp_path / "val" / "images" / "valid.png"
    write_image(valid)
    write_text(
        tmp_path / "train" / "labels" / "damaged.txt",
        "0 0.5 0.5 0.2 0.2\n",
    )
    write_text(
        tmp_path / "val" / "labels" / "valid.txt",
        "0 0.5 0.5 0.2 0.2\n",
    )

    manifest = parse_yolo_dataset(tmp_path)

    assert manifest.unreadable_image_paths == ["train/images/damaged.png"]
    assert [image.relative_path for image in manifest.images] == [
        "val/images/valid.png"
    ]
    assert manifest.summary.image_count == 2
    assert manifest.summary.annotation_count == 2
    assert manifest.summary.total_size_bytes == (
        damaged.stat().st_size + valid.stat().st_size
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
    prepare_dataset(tmp_path, yaml_content)

    with pytest.raises(DatasetParseError, match=message):
        parse_yolo_dataset(tmp_path)


def test_missing_or_invalid_data_yaml_has_clear_error(tmp_path: Path) -> None:
    with pytest.raises(DatasetParseError, match="contain data.yaml"):
        parse_yolo_dataset(tmp_path)

    write_text(tmp_path / "data.yaml", "names: [cat\n")
    with pytest.raises(DatasetParseError, match="invalid YAML"):
        parse_yolo_dataset(tmp_path)


def test_legacy_images_first_layout_is_rejected(tmp_path: Path) -> None:
    write_text(tmp_path / "data.yaml", "names: [cat]\n")
    write_image(tmp_path / "images" / "train" / "a.png")
    write_text(tmp_path / "labels" / "train" / "a.txt", "0 0.5 0.5 0.2 0.2\n")

    with pytest.raises(DatasetParseError, match="split 'train'"):
        parse_yolo_dataset(tmp_path)


def test_train_split_requires_images_and_labels_directories(tmp_path: Path) -> None:
    write_text(tmp_path / "data.yaml", "names: [cat]\n")
    write_image(tmp_path / "train" / "images" / "a.png")

    with pytest.raises(DatasetParseError, match="split 'train'.*images/ and labels/"):
        parse_yolo_dataset(tmp_path)


def test_val_and_test_splits_are_optional(tmp_path: Path) -> None:
    prepare_dataset(tmp_path)
    write_image(tmp_path / "train" / "images" / "only.jpg")
    write_text(
        tmp_path / "train" / "labels" / "only.txt",
        "0 0.5 0.5 0.2 0.2\n",
    )

    manifest = parse_yolo_dataset(tmp_path)

    assert [image.relative_path for image in manifest.images] == [
        "train/images/only.jpg"
    ]


def test_zip_and_dataset_root_regular_files_are_ignored(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    prepare_dataset(dataset)
    write_image(dataset / "train" / "images" / "a.png")
    write_text(dataset / "train" / "labels" / "a.txt", "0 0.5 0.5 0.2 0.2\n")
    write_text(tmp_path / "README.md", "archive notes\n")
    write_text(tmp_path / "manifest.json", "{}\n")
    write_text(dataset / "LICENSE", "demo license\n")
    (dataset / "preview.bin").write_bytes(b"ignored")

    manifest = parse_yolo_dataset(tmp_path)

    assert manifest.summary.image_count == 1
    assert manifest.images[0].relative_path == "train/images/a.png"


def test_optional_test_split_must_be_complete(tmp_path: Path) -> None:
    prepare_dataset(tmp_path)
    write_image(tmp_path / "train" / "images" / "a.png")
    (tmp_path / "test").mkdir()

    with pytest.raises(DatasetParseError, match="split 'test'"):
        parse_yolo_dataset(tmp_path)


def test_multiple_nested_data_yaml_files_are_rejected(tmp_path: Path) -> None:
    prepare_dataset(tmp_path / "one")
    prepare_dataset(tmp_path / "two")

    with pytest.raises(DatasetParseError, match="multiple data.yaml"):
        parse_yolo_dataset(tmp_path)


def test_direct_and_nested_data_yaml_are_ambiguous(tmp_path: Path) -> None:
    prepare_dataset(tmp_path)
    write_image(tmp_path / "train" / "images" / "a.png")
    prepare_dataset(tmp_path / "nested")

    with pytest.raises(DatasetParseError, match="multiple data.yaml"):
        parse_yolo_dataset(tmp_path)


def test_macos_metadata_data_yaml_is_ignored(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    prepare_dataset(dataset)
    write_image(dataset / "train" / "images" / "a.png")
    write_text(tmp_path / "__MACOSX" / "data.yaml", "metadata: true\n")

    manifest = parse_yolo_dataset(tmp_path)

    assert manifest.images[0].relative_path == "train/images/a.png"


def test_names_and_nc_contract_is_enforced(tmp_path: Path) -> None:
    prepare_dataset(tmp_path, "nc: 2\nnames: [cat]\n")
    with pytest.raises(DatasetParseError, match="nc.*2.*names.*1"):
        parse_yolo_dataset(tmp_path)

    write_text(tmp_path / "data.yaml", "nc: 1\n")
    with pytest.raises(DatasetParseError, match="missing required field 'names'"):
        parse_yolo_dataset(tmp_path)
