"""Core contracts for the VisionDoctor dataset audit MVP."""

from vision_doctor.config import Settings, get_settings
from vision_doctor.models import (
    AnnotationRecord,
    AuditReport,
    BoundingBox,
    DatasetManifest,
    DatasetSummary,
    Diagnosis,
    DistributionStats,
    DuplicateGroup,
    HealthScore,
    ImageRecord,
    Issue,
    PriorityFinding,
    RecommendedAction,
    ScoreBreakdown,
    Severity,
)

__all__ = [
    "AnnotationRecord",
    "AuditReport",
    "BoundingBox",
    "DatasetManifest",
    "DatasetSummary",
    "Diagnosis",
    "DistributionStats",
    "DuplicateGroup",
    "HealthScore",
    "ImageRecord",
    "Issue",
    "PriorityFinding",
    "RecommendedAction",
    "ScoreBreakdown",
    "Settings",
    "Severity",
    "get_settings",
]

__version__ = "0.1.0"
