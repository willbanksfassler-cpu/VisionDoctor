"""UI-independent orchestration for a complete VisionDoctor audit."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from vision_doctor.agent.client import diagnose_report
from vision_doctor.archive import extract_zip_safely
from vision_doctor.checkers.annotation import check_annotations
from vision_doctor.checkers.distribution import calculate_distribution
from vision_doctor.checkers.duplicates import find_duplicate_groups
from vision_doctor.checkers.image_quality import check_image_quality
from vision_doctor.config import Settings
from vision_doctor.models import AuditReport
from vision_doctor.parser import parse_yolo_dataset
from vision_doctor.scoring import calculate_health_score

if TYPE_CHECKING:
    from vision_doctor.agent.client import DatasetDoctorClient


def _build_threshold_snapshot(settings: Settings) -> dict[str, object]:
    """Capture the effective deterministic limits used for this audit."""

    upload = settings.upload.model_dump(mode="json")
    upload["allowed_image_extensions"] = sorted(
        settings.upload.allowed_image_extensions
    )
    return {
        "upload": upload,
        "image_quality": settings.image_quality.model_dump(mode="json"),
        "duplicate_detection": settings.duplicate_detection.model_dump(mode="json"),
    }


def run_pipeline(
    archive_path: str | Path,
    *,
    settings: Settings | None = None,
    temp_root: str | Path | None = None,
    run_doctor: bool = False,
    llm_client: DatasetDoctorClient | None = None,
) -> AuditReport:
    """Run the audit and optionally attach a validated Dataset Doctor diagnosis."""

    active = settings or Settings()
    source = Path(archive_path)
    with extract_zip_safely(
        source,
        limits=active.upload,
        temp_root=temp_root,
    ) as extracted:
        manifest = parse_yolo_dataset(
            extracted.root,
            source_archive=source.name,
            upload_limits=active.upload,
        )
        issues = check_annotations(manifest)
        issues.extend(
            check_image_quality(
                manifest,
                extracted.root,
                config=active.image_quality,
            )
        )
        duplicate_groups = find_duplicate_groups(
            manifest,
            extracted.root,
            config=active.duplicate_detection,
        )
        distribution = calculate_distribution(manifest)
        health_score = calculate_health_score(
            manifest,
            issues,
            duplicate_groups,
            distribution,
        )
        updated_summary = manifest.summary.model_copy(
            update={"issue_count": len(issues)}
        )
        manifest = manifest.model_copy(update={"summary": updated_summary})
        report = AuditReport(
            manifest=manifest,
            issues=issues,
            duplicate_groups=duplicate_groups,
            distribution=distribution,
            health_score=health_score,
            threshold_snapshot=_build_threshold_snapshot(active),
            diagnosis=None,
        )
        if not run_doctor:
            return report
        diagnosis = diagnose_report(report, active.llm, client=llm_client)
        return report.model_copy(update={"diagnosis": diagnosis})
