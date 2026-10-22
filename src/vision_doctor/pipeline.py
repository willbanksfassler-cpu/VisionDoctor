"""UI-independent orchestration for a complete VisionDoctor audit."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from vision_doctor.agent.client import diagnose_report_with_status
from vision_doctor.archive import extract_zip_safely
from vision_doctor.checkers.annotation import check_annotations
from vision_doctor.checkers.bbox_outliers import check_bbox_outliers
from vision_doctor.checkers.distribution import calculate_distribution
from vision_doctor.checkers.duplicates import (
    check_split_leakage,
    find_duplicate_groups,
)
from vision_doctor.checkers.image_quality import check_image_quality
from vision_doctor.config import Settings
from vision_doctor.knowledge.retrieval import retrieve_knowledge
from vision_doctor.models import AuditReport
from vision_doctor.parser import parse_yolo_dataset, resolve_yolo_dataset_root
from vision_doctor.repair_simulation import simulate_repairs
from vision_doctor.scoring import calculate_health_score, score_profile_from_config

if TYPE_CHECKING:
    from vision_doctor.agent.client import (
        DatasetDoctorClient,
        EvidenceQueryDatasetDoctorClient,
    )


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
        "bbox_outliers": settings.bbox_outliers.model_dump(mode="json"),
        "scoring": settings.scoring.model_dump(mode="json"),
        "knowledge": settings.knowledge.model_dump(mode="json"),
    }


def run_pipeline(
    archive_path: str | Path,
    *,
    settings: Settings | None = None,
    temp_root: str | Path | None = None,
    run_doctor: bool = False,
    llm_client: DatasetDoctorClient | EvidenceQueryDatasetDoctorClient | None = None,
) -> AuditReport:
    """Run the audit and optionally attach a validated Dataset Doctor diagnosis."""

    active = settings or Settings()
    source = Path(archive_path)
    with extract_zip_safely(
        source,
        limits=active.upload,
        temp_root=temp_root,
    ) as extracted:
        dataset_root = resolve_yolo_dataset_root(extracted.root)
        manifest = parse_yolo_dataset(
            dataset_root,
            source_archive=source.name,
            upload_limits=active.upload,
        )
        issues = check_annotations(manifest)
        issues.extend(
            check_bbox_outliers(
                manifest,
                config=active.bbox_outliers,
            )
        )
        issues.extend(
            check_image_quality(
                manifest,
                dataset_root,
                config=active.image_quality,
            )
        )
        duplicate_groups = find_duplicate_groups(
            manifest,
            dataset_root,
            config=active.duplicate_detection,
        )
        issues.extend(check_split_leakage(duplicate_groups))
        distribution = calculate_distribution(manifest)
        health_score = calculate_health_score(
            manifest,
            issues,
            duplicate_groups,
            distribution,
            profile=score_profile_from_config(active.scoring),
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
            repair_simulation=None,
            diagnosis=None,
        )
        repair_simulation = simulate_repairs(report)
        report = report.model_copy(
            update={"repair_simulation": repair_simulation}
        )
        knowledge_guidance = retrieve_knowledge(
            report,
            active.knowledge.profile,
            max_guidance_items=active.knowledge.max_guidance_items,
            max_questions=active.knowledge.max_questions,
        )
        report = report.model_copy(
            update={"knowledge_guidance": knowledge_guidance}
        )
        if not run_doctor:
            return report
        outcome = diagnose_report_with_status(
            report,
            active.llm,
            client=llm_client,
        )
        return report.model_copy(
            update={
                "diagnosis": outcome.diagnosis,
                "diagnosis_failure_stage": (
                    outcome.failure_stage.value
                    if outcome.failure_stage is not None
                    else None
                ),
                "diagnosis_mode": outcome.execution_mode,
            }
        )
