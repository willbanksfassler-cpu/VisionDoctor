"""Run the generated demo through the complete local VisionDoctor pipeline."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from generate_demo_dataset import generate_demo_zip

from vision_doctor.models import AuditReport
from vision_doctor.pipeline import run_pipeline

EXPECTED_CODES = {
    "LABEL_MISSING",
    "LABEL_ORPHAN",
    "LABEL_EMPTY",
    "LABEL_PARSE_ERROR",
    "CLASS_ID_INVALID",
    "BBOX_OUT_OF_RANGE",
    "BBOX_TINY",
    "IMAGE_UNREADABLE",
    "IMAGE_BLURRY",
    "IMAGE_DARK",
    "IMAGE_BRIGHT",
    "IMAGE_LOW_RESOLUTION",
}


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="vision-doctor-smoke-") as directory:
        temporary_root = Path(directory)
        archive = generate_demo_zip(temporary_root / "demo.zip")
        report = run_pipeline(archive, temp_root=temporary_root)
        serialized = report.model_dump_json()
        AuditReport.model_validate_json(serialized)
        actual_codes = {issue.code for issue in report.issues}
        missing_codes = sorted(EXPECTED_CODES - actual_codes)
        if missing_codes:
            raise RuntimeError(f"Demo pipeline missed expected Issue codes: {missing_codes}")
        duplicate_kinds = {group.kind for group in report.duplicate_groups}
        if duplicate_kinds != {"exact", "near"}:
            raise RuntimeError(
                f"Expected exact and near duplicate groups, got {duplicate_kinds}."
            )
        summary = {
            "schema_version": report.schema_version,
            "images": report.manifest.summary.image_count,
            "issues": len(report.issues),
            "issue_codes": sorted(actual_codes),
            "duplicate_kinds": sorted(duplicate_kinds),
            "health_score": report.health_score.overall,
            "grade": report.health_score.grade,
            "diagnosis": report.diagnosis,
        }
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
