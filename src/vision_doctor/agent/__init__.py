"""Single Dataset Doctor with validated LLM and deterministic fallback paths."""

from vision_doctor.agent.client import (
    DatasetDoctorClient,
    DiagnosisOutcome,
    EvidenceQueryDatasetDoctorClient,
    EvidenceToolCall,
    EvidenceToolTurn,
    LLMFailureStage,
    OpenAICompatibleDatasetDoctorClient,
    diagnose_report,
    diagnose_report_with_status,
)
from vision_doctor.agent.evidence_tools import EvidenceQueryService
from vision_doctor.agent.fallback import build_fallback_diagnosis
from vision_doctor.agent.validator import validate_diagnosis_facts

__all__ = [
    "DatasetDoctorClient",
    "DiagnosisOutcome",
    "EvidenceQueryDatasetDoctorClient",
    "EvidenceQueryService",
    "EvidenceToolCall",
    "EvidenceToolTurn",
    "LLMFailureStage",
    "OpenAICompatibleDatasetDoctorClient",
    "build_fallback_diagnosis",
    "diagnose_report",
    "diagnose_report_with_status",
    "validate_diagnosis_facts",
]
