"""Evidence tests for every annotation checker issue code."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from vision_doctor.checkers.annotation import (
    BBOX_CROSSES_BORDER,
    BBOX_NON_POSITIVE,
    BBOX_OUT_OF_RANGE,
    BBOX_TINY,
    CLASS_ID_INVALID,
    LABEL_EMPTY,
    LABEL_MISSING,
    LABEL_ORPHAN,
    LABEL_PARSE_ERROR,
    AnnotationCheckConfig,
    check_annotations,
)
from vision_doctor.models import Severity
from vision_doctor.parser import parse_yolo_dataset


def write_image(path: Path, *, size: tuple[int, int] = (100, 100)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color=(40, 60, 80)).save(path)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_issue_fixture(root: Path) -> None:
    write_text(root / "data.yaml", "names: [cat]\n")
    cases = {
        "empty": "  \n",
        "parse": "0 0.5 0.5 0.2\n",
        "class": "9 0.5 0.5 0.2 0.2\n",
        "nonpositive": "0 0.5 0.5 0 0.2\n",
        "outofrange": "0 1.2 0.5 0.2 0.2\n",
        "border": "0 0.05 0.5 0.2 0.2\n",
        "tiny": "0 0.5 0.5 0.005 0.005\n",
        "normal": "0 0.5 0.5 0.2 0.2\n",
    }
    write_image(root / "images" / "missing.jpg")
    for stem, label in cases.items():
        write_image(root / "images" / f"{stem}.jpg")
        write_text(root / "labels" / f"{stem}.txt", label)
    write_text(root / "labels" / "orphan.txt", "0 0.5 0.5 0.2 0.2\n")


def test_every_required_issue_code_has_positive_evidence(tmp_path: Path) -> None:
    build_issue_fixture(tmp_path)
    manifest = parse_yolo_dataset(tmp_path)

    issues = check_annotations(manifest)
    by_code = {issue.code: issue for issue in issues}

    assert set(by_code) == {
        LABEL_MISSING,
        LABEL_ORPHAN,
        LABEL_EMPTY,
        LABEL_PARSE_ERROR,
        CLASS_ID_INVALID,
        BBOX_NON_POSITIVE,
        BBOX_OUT_OF_RANGE,
        BBOX_CROSSES_BORDER,
        BBOX_TINY,
    }
    assert by_code[LABEL_EMPTY].severity is Severity.INFO
    assert "may be an intentional negative sample" in by_code[LABEL_EMPTY].message
    assert by_code[LABEL_PARSE_ERROR].annotation_line == 1
    assert by_code[BBOX_OUT_OF_RANGE].bbox == (1.2, 0.5, 0.2, 0.2)
    assert by_code[BBOX_TINY].metrics["width_pixels"] == 0.5
    assert by_code[LABEL_ORPHAN].relative_path == "labels/orphan.txt"
    assert all(issue.issue_id.startswith("annotation-") for issue in issues)
    assert all(issue.relative_path for issue in issues)
    assert all(issue.suggested_action for issue in issues)
    assert all(isinstance(issue.metrics, dict) for issue in issues)
    assert len({issue.issue_id for issue in issues}) == len(issues)
    row_codes = {
        LABEL_PARSE_ERROR,
        CLASS_ID_INVALID,
        BBOX_NON_POSITIVE,
        BBOX_OUT_OF_RANGE,
        BBOX_CROSSES_BORDER,
        BBOX_TINY,
    }
    assert all(by_code[code].annotation_line is not None for code in row_codes)


def test_normal_label_has_no_false_positive(tmp_path: Path) -> None:
    write_text(tmp_path / "data.yaml", "names: [cat]\n")
    write_image(tmp_path / "images" / "normal.jpg")
    write_text(tmp_path / "labels" / "normal.txt", "0 0.5 0.5 0.2 0.2\n")

    issues = check_annotations(parse_yolo_dataset(tmp_path))

    assert issues == []


def test_damaged_label_does_not_block_other_images(tmp_path: Path) -> None:
    write_text(tmp_path / "data.yaml", "names: [cat]\n")
    write_image(tmp_path / "images" / "bad.jpg")
    write_image(tmp_path / "images" / "tiny.jpg")
    write_text(tmp_path / "labels" / "bad.txt", "not a yolo row\n")
    write_text(tmp_path / "labels" / "tiny.txt", "0 0.5 0.5 0.001 0.001\n")

    issues = check_annotations(parse_yolo_dataset(tmp_path))

    assert {issue.code for issue in issues} == {LABEL_PARSE_ERROR, BBOX_TINY}


def test_issue_ids_are_stable_and_tiny_thresholds_are_configurable(
    tmp_path: Path,
) -> None:
    write_text(tmp_path / "data.yaml", "names: [cat]\n")
    write_image(tmp_path / "images" / "object.jpg")
    write_text(tmp_path / "labels" / "object.txt", "0 0.5 0.5 0.05 0.05\n")
    manifest = parse_yolo_dataset(tmp_path)

    default_issues = check_annotations(manifest)
    strict_config = AnnotationCheckConfig(
        min_bbox_width_pixels=6,
        min_bbox_height_pixels=6,
        min_bbox_area_pixels=36,
    )
    first = check_annotations(manifest, config=strict_config)
    second = check_annotations(manifest, config=strict_config)

    assert default_issues == []
    assert [issue.code for issue in first] == [BBOX_TINY]
    assert [issue.issue_id for issue in first] == [issue.issue_id for issue in second]
    assert first[0].annotation_line == 1
    assert first[0].bbox == (0.5, 0.5, 0.05, 0.05)
