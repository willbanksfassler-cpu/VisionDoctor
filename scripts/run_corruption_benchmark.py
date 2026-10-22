"""Run VisionDoctor against a deterministic controlled-corruption benchmark."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import tracemalloc
import zipfile
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scripts.generate_corruption_benchmark import (
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_SEED,
    PROFILE_IMAGE_COUNTS,
    generate_corruption_benchmark,
)
from vision_doctor.config import Settings
from vision_doctor.evaluation import (
    BenchmarkGroundTruth,
    DuplicateExpectation,
    IssueExpectation,
    QualityModeComparison,
    evaluate_benchmark_report,
    render_benchmark_markdown,
)
from vision_doctor.pipeline import run_pipeline


def _write_reproducible_zip(
    members: dict[str, bytes],
    destination: Path,
) -> None:
    with zipfile.ZipFile(
        destination,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as archive:
        for name, content in sorted(members.items()):
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(
                info,
                content,
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=6,
            )


def _move_member(
    members: dict[str, bytes],
    old_name: str,
    new_name: str,
) -> None:
    members[new_name] = members.pop(old_name)


def _extend_stage11_benchmark(artifacts) -> BenchmarkGroundTruth:
    """Add stage-11 injections without changing the stage-10 generator."""

    with zipfile.ZipFile(artifacts.corrupted_archive, "r") as archive:
        members = {
            item.filename: archive.read(item)
            for item in archive.infolist()
            if not item.is_dir()
        }
    _move_member(
        members,
        "dataset/train/images/014_exact_b.jpg",
        "dataset/val/images/014_exact_b.jpg",
    )
    _move_member(
        members,
        "dataset/train/labels/014_exact_b.txt",
        "dataset/val/labels/014_exact_b.txt",
    )
    _move_member(
        members,
        "dataset/train/images/015_near.jpg",
        "dataset/test/images/015_near.jpg",
    )
    _move_member(
        members,
        "dataset/train/labels/015_near.txt",
        "dataset/test/labels/015_near.txt",
    )
    members["dataset/train/labels/016_clean.txt"] = (
        b"0 0.5 0.5 0.04 0.04\n"
    )
    members["dataset/train/labels/017_clean.txt"] = b"0 0.5 0.5 0.5 0.1\n"
    _write_reproducible_zip(members, artifacts.corrupted_archive)

    ground_truth = artifacts.ground_truth
    duplicate_groups = [
        DuplicateExpectation(
            kind="exact",
            image_ids=[
                "train/images/013_exact_a.jpg",
                "val/images/014_exact_b.jpg",
            ],
        ),
        DuplicateExpectation(
            kind="near",
            image_ids=[
                "train/images/013_exact_a.jpg",
                "test/images/015_near.jpg",
            ],
        ),
    ]
    issues = [
        *ground_truth.issues,
        IssueExpectation(
            code="SPLIT_LEAKAGE_EXACT",
            relative_path="train/images/013_exact_a.jpg",
            image_id="train/images/013_exact_a.jpg",
        ),
        IssueExpectation(
            code="SPLIT_LEAKAGE_NEAR",
            relative_path="train/images/013_exact_a.jpg",
            image_id="train/images/013_exact_a.jpg",
        ),
        IssueExpectation(
            code="BBOX_AREA_OUTLIER",
            relative_path="train/labels/007_bbox_tiny.txt",
            annotation_line=1,
            image_id="train/images/007_bbox_tiny.jpg",
        ),
        IssueExpectation(
            code="BBOX_AREA_OUTLIER",
            relative_path="train/labels/016_clean.txt",
            annotation_line=1,
            image_id="train/images/016_clean.jpg",
        ),
        IssueExpectation(
            code="BBOX_ASPECT_RATIO_OUTLIER",
            relative_path="train/labels/017_clean.txt",
            annotation_line=1,
            image_id="train/images/017_clean.jpg",
        ),
    ]
    extended = ground_truth.model_copy(
        update={
            "issues": issues,
            "duplicate_groups": duplicate_groups,
            "notes": [
                *ground_truth.notes,
                (
                    "Stage 11 adds cross-split duplicate leakage and "
                    "class-conditional bbox outlier injections."
                ),
            ],
        }
    )
    artifacts.ground_truth_path.write_text(
        extended.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return extended


def _run_pipeline_once(archive_path: Path, settings: Settings):
    with tempfile.TemporaryDirectory(
        prefix="vision-doctor-benchmark-run-"
    ) as directory:
        started = time.perf_counter()
        report = run_pipeline(
            archive_path,
            settings=settings,
            temp_root=directory,
            run_doctor=False,
        )
        return report, time.perf_counter() - started


def _comparison(
    mode: str,
    report,
    result,
    total_seconds: float,
) -> QualityModeComparison:
    counts = Counter(issue.code for issue in report.issues)
    return QualityModeComparison(
        mode=mode,
        issue_counts=dict(sorted(counts.items())),
        micro_average=result.evaluation.micro_average,
        macro_average=result.evaluation.macro_average,
        unmatched_count=len(result.evaluation.unmatched),
        total_seconds=round(total_seconds, 6),
    )


def run_benchmark(
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    *,
    profile: str = "quick",
    seed: int = DEFAULT_SEED,
):
    """Generate, execute, evaluate, and persist one benchmark profile."""

    artifacts = generate_corruption_benchmark(
        output_root,
        profile=profile,
        seed=seed,
    )
    _extend_stage11_benchmark(artifacts)
    ground_truth = BenchmarkGroundTruth.model_validate_json(
        artifacts.ground_truth_path.read_text(encoding="utf-8")
    )
    base_settings = Settings(_env_file=None)
    fixed_settings = base_settings.model_copy(
        update={
            "image_quality": base_settings.image_quality.model_copy(
                update={"mode": "fixed"}
            )
        }
    )
    with tempfile.TemporaryDirectory(
        prefix="vision-doctor-benchmark-run-"
    ) as directory:
        tracemalloc.start()
        started = time.perf_counter()
        try:
            report = run_pipeline(
                artifacts.corrupted_archive,
                settings=fixed_settings,
                temp_root=directory,
                run_doctor=False,
            )
        finally:
            total_seconds = time.perf_counter() - started
            _, peak_memory = tracemalloc.get_traced_memory()
            tracemalloc.stop()

    result = evaluate_benchmark_report(
        ground_truth,
        report,
        total_seconds=total_seconds,
        python_peak_memory_bytes=peak_memory,
    )
    adaptive_settings = base_settings.model_copy(
        update={
            "image_quality": base_settings.image_quality.model_copy(
                update={"mode": "adaptive"}
            )
        }
    )
    adaptive_report, adaptive_seconds = _run_pipeline_once(
        artifacts.corrupted_archive,
        adaptive_settings,
    )
    adaptive_result = evaluate_benchmark_report(
        ground_truth,
        adaptive_report,
        total_seconds=adaptive_seconds,
        python_peak_memory_bytes=0,
    )
    result = result.model_copy(
        update={
            "quality_mode_comparison": [
                _comparison("fixed", report, result, total_seconds),
                _comparison(
                    "adaptive",
                    adaptive_report,
                    adaptive_result,
                    adaptive_seconds,
                ),
            ]
        }
    )
    json_path = artifacts.output_directory / "result.json"
    markdown_path = artifacts.output_directory / "result.md"
    json_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    markdown_path.write_text(
        render_benchmark_markdown(result),
        encoding="utf-8",
    )
    return result, json_path, markdown_path


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
    result, json_path, markdown_path = run_benchmark(
        args.output_root,
        profile=args.profile,
        seed=args.seed,
    )
    print(
        json.dumps(
            {
                "profile": result.profile,
                "seed": result.seed,
                "image_count": result.image_count,
                "micro": result.evaluation.micro_average.model_dump(),
                "macro": result.evaluation.macro_average.model_dump(),
                "unmatched_count": len(result.evaluation.unmatched),
                "distribution_matches_ground_truth": (
                    result.evaluation.distribution_matches_ground_truth
                ),
                "total_seconds": result.performance.total_seconds,
                "seconds_per_image": result.performance.seconds_per_image,
                "python_peak_memory_bytes": (
                    result.performance.python_peak_memory_bytes
                ),
                "quality_mode_comparison": [
                    item.model_dump()
                    for item in result.quality_mode_comparison
                ],
                "result_json": str(json_path),
                "result_markdown": str(markdown_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
