"""Single Dataset Doctor with validated LLM and deterministic fallback paths."""

from vision_doctor.agent.client import (
    DatasetDoctorClient,
    DiagnosisOutcome,
    LLMFailureStage,
    OpenAICompatibleDatasetDoctorClient,
    diagnose_report,
    diagnose_report_with_status,
)
from vision_doctor.agent.fallback import build_fallback_diagnosis

__all__ = [
    "DatasetDoctorClient",
    "DiagnosisOutcome",
    "LLMFailureStage",
    "OpenAICompatibleDatasetDoctorClient",
    "build_fallback_diagnosis",
    "diagnose_report",
    "diagnose_report_with_status",
]
