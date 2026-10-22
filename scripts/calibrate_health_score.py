"""Evaluate Health Score candidates from an existing benchmark result."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from scripts.generate_corruption_benchmark import DEFAULT_OUTPUT_ROOT
from vision_doctor.evaluation import BenchmarkResult
from vision_doctor.scoring_calibration import (
    calibrate_score_profiles,
    render_calibration_markdown,
)


def run_calibration(
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    *,
    profile: str = "quick",
):
    """Read benchmark evidence and write non-mutating calibration artifacts."""

    directory = Path(output_root) / profile
    benchmark_path = directory / "result.json"
    if not benchmark_path.is_file():
        raise FileNotFoundError(
            f"Benchmark result not found: {benchmark_path}. Run the benchmark first."
        )
    benchmark = BenchmarkResult.model_validate_json(
        benchmark_path.read_text(encoding="utf-8")
    )
    report = calibrate_score_profiles(benchmark)
    json_path = directory / "score_calibration.json"
    markdown_path = directory / "score_calibration.md"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    markdown_path.write_text(
        render_calibration_markdown(report),
        encoding="utf-8",
    )
    return report, json_path, markdown_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("quick", "standard", "scale"),
        default="quick",
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args()
    report, json_path, markdown_path = run_calibration(
        args.output_root,
        profile=args.profile,
    )
    print(
        json.dumps(
            {
                "profile": report.benchmark_profile,
                "candidate_count": len(report.candidates),
                "monotonicity_checks": sum(
                    len(candidate.monotonicity.checks)
                    for candidate in report.candidates
                ),
                "monotonicity_passed": all(
                    candidate.monotonicity.passed
                    for candidate in report.candidates
                ),
                "recommended_candidate": report.recommended_candidate,
                "production_configuration_modified": (
                    report.production_configuration_modified
                ),
                "result_json": str(json_path),
                "result_markdown": str(markdown_path),
                "synthetic_benchmark_warning": (
                    "Synthetic calibration cannot replace real business calibration."
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
