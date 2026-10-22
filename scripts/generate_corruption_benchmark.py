"""Generate deterministic clean and controlled-corruption YOLO benchmarks."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from vision_doctor.evaluation import (
    BenchmarkGroundTruth,
    DistributionExpectation,
    DuplicateExpectation,
    IssueExpectation,
)

DEFAULT_SEED = 20261022
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "benchmarks" / "generated"
PROFILE_IMAGE_COUNTS = {"quick": 40, "standard": 160, "scale": 800}

_CASE_NAMES = (
    "label_missing",
    "label_empty",
    "label_parse_error",
    "class_id_invalid",
    "bbox_non_positive",
    "bbox_out_of_range",
    "bbox_crosses_border",
    "bbox_tiny",
    "image_unreadable",
    "image_blurry",
    "image_dark",
    "image_bright",
    "image_low_resolution",
    "exact_a",
    "exact_b",
    "near",
)


@dataclass(frozen=True)
class BenchmarkArtifacts:
    """Paths produced by a deterministic benchmark generation run."""

    output_directory: Path
    clean_archive: Path
    corrupted_archive: Path
    ground_truth_path: Path
    ground_truth: BenchmarkGroundTruth


def _stem(index: int) -> str:
    if index < len(_CASE_NAMES):
        return f"{index:03d}_{_CASE_NAMES[index]}"
    return f"{index:03d}_clean"


def _split(index: int, image_count: int) -> str:
    train_end = max(len(_CASE_NAMES), int(image_count * 0.7))
    val_end = max(train_end + 1, int(image_count * 0.9))
    if index < train_end:
        return "train"
    if index < val_end:
        return "val"
    return "test"


def _relative_image(index: int, image_count: int) -> str:
    return f"{_split(index, image_count)}/images/{_stem(index)}.jpg"


def _relative_label(index: int, image_count: int) -> str:
    return f"{_split(index, image_count)}/labels/{_stem(index)}.txt"


def _noise_pixels(seed: int, index: int, size: int = 320) -> np.ndarray:
    rng = np.random.default_rng(seed + index * 104_729)
    return rng.integers(0, 256, size=(size, size, 3), dtype=np.uint8)


def _save_jpeg(path: Path, pixels: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(pixels.astype(np.uint8), mode="RGB").save(
        path,
        format="JPEG",
        quality=88,
        optimize=False,
        progressive=False,
        subsampling=0,
    )


def _write_clean_dataset(root: Path, image_count: int, seed: int) -> None:
    dataset = root / "dataset"
    dataset.mkdir(parents=True)
    (dataset / "data.yaml").write_text(
        "name: corruption-benchmark\nnc: 3\nnames: [majority, minority, unused]\n",
        encoding="utf-8",
    )
    (dataset / "README.txt").write_text(
        "Synthetic clean source for controlled corruption.\n",
        encoding="utf-8",
    )
    (root / "packaging-note.json").write_text(
        '{"synthetic":true,"internet_downloads":false}\n',
        encoding="utf-8",
    )
    for index in range(image_count):
        image_path = dataset / _relative_image(index, image_count)
        label_path = dataset / _relative_label(index, image_count)
        _save_jpeg(image_path, _noise_pixels(seed, index))
        label_path.parent.mkdir(parents=True, exist_ok=True)
        label_path.write_text(
            f"{index % 3} 0.5 0.5 0.25 0.25\n",
            encoding="utf-8",
        )


def _write_corruptions(
    root: Path,
    image_count: int,
    seed: int,
) -> BenchmarkGroundTruth:
    dataset = root / "dataset"
    for index in range(image_count):
        class_id = 1 if index == 15 else 0
        (dataset / _relative_label(index, image_count)).write_text(
            f"{class_id} 0.5 0.5 0.25 0.25\n",
            encoding="utf-8",
        )

    image_paths = [
        _relative_image(index, image_count) for index in range(len(_CASE_NAMES))
    ]
    label_paths = [
        _relative_label(index, image_count) for index in range(len(_CASE_NAMES))
    ]

    (dataset / label_paths[0]).unlink()
    (dataset / label_paths[1]).write_text("", encoding="utf-8")
    (dataset / label_paths[2]).write_text(
        "0 0.5 0.5 0.25\n", encoding="utf-8"
    )
    (dataset / label_paths[3]).write_text(
        "9 0.5 0.5 0.25 0.25\n", encoding="utf-8"
    )
    (dataset / label_paths[4]).write_text(
        "0 0.5 0.5 0.0 0.25\n", encoding="utf-8"
    )
    (dataset / label_paths[5]).write_text(
        "0 1.2 0.5 0.25 0.25\n", encoding="utf-8"
    )
    (dataset / label_paths[6]).write_text(
        "0 0.05 0.5 0.2 0.2\n", encoding="utf-8"
    )
    (dataset / label_paths[7]).write_text(
        "0 0.5 0.5 0.001 0.001\n", encoding="utf-8"
    )

    (dataset / image_paths[8]).write_bytes(b"controlled unreadable image")
    _save_jpeg(dataset / image_paths[9], np.full((320, 320, 3), 128))
    dark_rng = np.random.default_rng(seed + 900_001)
    _save_jpeg(
        dataset / image_paths[10],
        dark_rng.integers(0, 81, size=(320, 320, 3), dtype=np.uint8),
    )
    bright_rng = np.random.default_rng(seed + 900_002)
    _save_jpeg(
        dataset / image_paths[11],
        bright_rng.integers(180, 256, size=(320, 320, 3), dtype=np.uint8),
    )
    _save_jpeg(dataset / image_paths[12], _noise_pixels(seed, 12, size=160))

    exact_source = dataset / image_paths[13]
    shutil.copyfile(exact_source, dataset / image_paths[14])
    with Image.open(exact_source) as source:
        near_pixels = np.asarray(source.convert("RGB"), dtype=np.uint8).copy()
    near_pixels[:4, :4, :] = 255 - near_pixels[:4, :4, :]
    _save_jpeg(dataset / image_paths[15], near_pixels)

    issues = [
        IssueExpectation(
            code="LABEL_MISSING",
            relative_path=label_paths[0],
            image_id=image_paths[0],
        ),
        IssueExpectation(
            code="LABEL_EMPTY",
            relative_path=label_paths[1],
            image_id=image_paths[1],
        ),
        IssueExpectation(
            code="LABEL_PARSE_ERROR",
            relative_path=label_paths[2],
            annotation_line=1,
            image_id=image_paths[2],
        ),
        IssueExpectation(
            code="CLASS_ID_INVALID",
            relative_path=label_paths[3],
            annotation_line=1,
            image_id=image_paths[3],
        ),
        IssueExpectation(
            code="BBOX_NON_POSITIVE",
            relative_path=label_paths[4],
            annotation_line=1,
            image_id=image_paths[4],
        ),
        IssueExpectation(
            code="BBOX_OUT_OF_RANGE",
            relative_path=label_paths[5],
            annotation_line=1,
            image_id=image_paths[5],
        ),
        IssueExpectation(
            code="BBOX_CROSSES_BORDER",
            relative_path=label_paths[6],
            annotation_line=1,
            image_id=image_paths[6],
        ),
        IssueExpectation(
            code="BBOX_TINY",
            relative_path=label_paths[7],
            annotation_line=1,
            image_id=image_paths[7],
        ),
        IssueExpectation(
            code="IMAGE_UNREADABLE",
            relative_path=image_paths[8],
            image_id=image_paths[8],
        ),
        IssueExpectation(
            code="IMAGE_BLURRY",
            relative_path=image_paths[9],
            image_id=image_paths[9],
        ),
        IssueExpectation(
            code="IMAGE_DARK",
            relative_path=image_paths[10],
            image_id=image_paths[10],
        ),
        IssueExpectation(
            code="IMAGE_BRIGHT",
            relative_path=image_paths[11],
            image_id=image_paths[11],
        ),
        IssueExpectation(
            code="IMAGE_LOW_RESOLUTION",
            relative_path=image_paths[12],
            image_id=image_paths[12],
        ),
    ]
    majority_count = image_count - 8
    return BenchmarkGroundTruth(
        profile=next(
            name
            for name, count in PROFILE_IMAGE_COUNTS.items()
            if count == image_count
        ),
        seed=seed,
        image_count=image_count,
        issues=issues,
        duplicate_groups=[
            DuplicateExpectation(
                kind="exact",
                image_ids=[image_paths[13], image_paths[14]],
            ),
            DuplicateExpectation(
                kind="near",
                image_ids=[image_paths[13], image_paths[15]],
            ),
        ],
        distribution=DistributionExpectation(
            class_counts={0: majority_count, 1: 1, 2: 0},
            rare_class_ids=[1],
            zero_instance_class_ids=[2],
            min_imbalance_index=float(majority_count),
        ),
        notes=[
            (
                "Ground truth is defined by deterministic injections, not inferred "
                "from VisionDoctor output."
            ),
            "The benchmark is synthetic and does not represent real business data.",
        ],
    )


def _write_reproducible_zip(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        destination,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as archive:
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            relative = path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(
                info,
                path.read_bytes(),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=6,
            )


def generate_corruption_benchmark(
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    *,
    profile: str = "quick",
    seed: int = DEFAULT_SEED,
) -> BenchmarkArtifacts:
    """Generate clean/corrupted archives and explicit injected ground truth."""

    if profile not in PROFILE_IMAGE_COUNTS:
        choices = ", ".join(PROFILE_IMAGE_COUNTS)
        raise ValueError(f"Unknown profile {profile!r}; expected one of: {choices}.")
    image_count = PROFILE_IMAGE_COUNTS[profile]
    output_directory = Path(output_root) / profile
    output_directory.mkdir(parents=True, exist_ok=True)
    clean_archive = output_directory / "clean.zip"
    corrupted_archive = output_directory / "corrupted.zip"
    ground_truth_path = output_directory / "ground_truth.json"

    with tempfile.TemporaryDirectory(prefix="vision-doctor-benchmark-") as directory:
        work = Path(directory)
        clean_root = work / "clean"
        corrupted_root = work / "corrupted"
        _write_clean_dataset(clean_root, image_count, seed)
        shutil.copytree(clean_root, corrupted_root)
        ground_truth = _write_corruptions(corrupted_root, image_count, seed)
        _write_reproducible_zip(clean_root, clean_archive)
        _write_reproducible_zip(corrupted_root, corrupted_archive)

    ground_truth_path.write_text(
        ground_truth.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return BenchmarkArtifacts(
        output_directory=output_directory,
        clean_archive=clean_archive,
        corrupted_archive=corrupted_archive,
        ground_truth_path=ground_truth_path,
        ground_truth=ground_truth,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=tuple(PROFILE_IMAGE_COUNTS),
        default="quick",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    artifacts = generate_corruption_benchmark(
        args.output_root,
        profile=args.profile,
        seed=args.seed,
    )
    print(
        json.dumps(
            {
                "profile": args.profile,
                "seed": args.seed,
                "image_count": artifacts.ground_truth.image_count,
                "clean_archive": str(artifacts.clean_archive),
                "corrupted_archive": str(artifacts.corrupted_archive),
                "ground_truth": str(artifacts.ground_truth_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
