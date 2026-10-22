"""Validated, serialization-friendly data contracts for VisionDoctor."""

from __future__ import annotations

import math
from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    RootModel,
    field_validator,
    model_validator,
)


class ContractModel(BaseModel):
    """Shared strictness for all object-shaped public contracts."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class Severity(str, Enum):
    """Normalized issue severity used by checks, reports, and the UI."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class KnowledgeProfile(str, Enum):
    """Fixed scenario identifiers; values are never treated as file paths."""

    GENERIC = "generic"
    INDUSTRIAL_INSPECTION = "industrial_inspection"
    RETAIL_DETECTION = "retail_detection"
    SMALL_OBJECT_DETECTION = "small_object_detection"


class KnowledgeProvenance(ContractModel):
    """Auditable origin metadata without implying empirical validation."""

    source_type: Literal["general_guidance", "curated_project_guidance"]
    source_name: str = Field(min_length=1, max_length=160)
    source_reference: str = Field(min_length=1, max_length=500)
    evidence_level: Literal["general_guidance", "documented_practice"]


class KnowledgeGuidanceEntry(ContractModel):
    """One bounded advisory entry selected from a validated local pack."""

    guidance_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")
    title: str = Field(min_length=1, max_length=160)
    guidance: str = Field(min_length=1, max_length=800)
    applicable_issue_codes: list[str] = Field(default_factory=list, max_length=30)
    evidence_signals: list[
        Literal[
            "always",
            "class_distribution",
            "bbox_statistics",
            "image_quality",
            "split_leakage",
            "repair_simulation",
        ]
    ] = Field(default_factory=list, max_length=6)
    requires_human_confirmation: bool = True

    @field_validator("applicable_issue_codes")
    @classmethod
    def validate_issue_codes(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("knowledge entry issue codes must be unique")
        if any(
            not code or not code.replace("_", "").isalnum() or code.upper() != code
            for code in value
        ):
            raise ValueError("knowledge entry issue codes must use stable uppercase codes")
        return value


class KnowledgePack(ContractModel):
    """Versioned local scenario guidance validated before retrieval."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    profile_id: KnowledgeProfile
    display_name: str = Field(min_length=1, max_length=120)
    applicable_issue_codes: list[str] = Field(min_length=1, max_length=100)
    review_guidance: list[KnowledgeGuidanceEntry] = Field(min_length=1, max_length=30)
    recommended_questions: list[str] = Field(min_length=1, max_length=20)
    caveats: list[str] = Field(min_length=1, max_length=20)
    source: str = Field(min_length=1, max_length=300)
    provenance: KnowledgeProvenance

    @model_validator(mode="after")
    def validate_pack_consistency(self) -> KnowledgePack:
        if len(set(self.applicable_issue_codes)) != len(self.applicable_issue_codes):
            raise ValueError("knowledge pack issue codes must be unique")
        guidance_ids = [item.guidance_id for item in self.review_guidance]
        if len(set(guidance_ids)) != len(guidance_ids):
            raise ValueError("knowledge guidance IDs must be unique within a pack")
        known_codes = set(self.applicable_issue_codes)
        if any(
            not set(item.applicable_issue_codes) <= known_codes
            for item in self.review_guidance
        ):
            raise ValueError("guidance entry contains an undeclared issue code")
        return self


class KnowledgeGuidanceContext(ContractModel):
    """Retrieved advisory context, kept separate from detection facts."""

    profile_id: KnowledgeProfile
    display_name: str = Field(min_length=1, max_length=120)
    pack_schema_version: Literal["1.0.0"] = "1.0.0"
    used_guidance_entry_ids: list[str] = Field(default_factory=list, max_length=10)
    guidance_entries: list[KnowledgeGuidanceEntry] = Field(
        default_factory=list,
        max_length=10,
    )
    recommended_questions: list[str] = Field(default_factory=list, max_length=10)
    caveats: list[str] = Field(default_factory=list, max_length=10)
    source: str = Field(min_length=1, max_length=300)
    provenance: KnowledgeProvenance
    fallback_reason: Literal["unknown_profile"] | None = None
    advisory_notice: str = Field(
        default=(
            "Scenario guidance is advisory and is not a detection fact, an applied "
            "repair, or a model-performance guarantee."
        ),
        min_length=1,
    )

    @model_validator(mode="after")
    def keep_entry_ids_consistent(self) -> KnowledgeGuidanceContext:
        actual = [entry.guidance_id for entry in self.guidance_entries]
        if self.used_guidance_entry_ids != actual:
            raise ValueError("used guidance IDs must match retrieved entry order")
        return self


class BoundingBox(RootModel[tuple[float, float, float, float]]):
    """A YOLO ``(x_center, y_center, width, height)`` normalized box."""

    @model_validator(mode="after")
    def validate_normalized_box(self) -> BoundingBox:
        x_center, y_center, width, height = self.root
        values = (x_center, y_center, width, height)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("bounding-box values must be finite")
        if not 0.0 <= x_center <= 1.0 or not 0.0 <= y_center <= 1.0:
            raise ValueError("bounding-box center must be normalized to [0, 1]")
        if not 0.0 < width <= 1.0 or not 0.0 < height <= 1.0:
            raise ValueError("bounding-box size must be normalized to (0, 1]")
        if x_center - width / 2 < 0.0 or x_center + width / 2 > 1.0:
            raise ValueError("bounding box exceeds horizontal image bounds")
        if y_center - height / 2 < 0.0 or y_center + height / 2 > 1.0:
            raise ValueError("bounding box exceeds vertical image bounds")
        return self

    @property
    def x_center(self) -> float:
        return self.root[0]

    @property
    def y_center(self) -> float:
        return self.root[1]

    @property
    def width(self) -> float:
        return self.root[2]

    @property
    def height(self) -> float:
        return self.root[3]


class AnnotationRecord(ContractModel):
    """One valid YOLO detection annotation tied to its source line."""

    image_id: str = Field(min_length=1)
    class_id: int = Field(ge=0)
    bbox: BoundingBox
    source_path: str = Field(min_length=1)
    line_number: int = Field(ge=1)


class ImageRecord(ContractModel):
    """Metadata for one successfully discovered image."""

    image_id: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    file_size_bytes: int = Field(ge=0)
    annotation_count: int = Field(default=0, ge=0)
    label_path: str | None = None
    label_status: Literal["missing", "empty", "present"] = "missing"
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    perceptual_hash: str | None = None


class DatasetSummary(ContractModel):
    """Top-level counts shown consistently across outputs."""

    image_count: int = Field(ge=0)
    label_file_count: int = Field(ge=0)
    annotation_count: int = Field(ge=0)
    class_count: int = Field(ge=0)
    issue_count: int = Field(default=0, ge=0)
    total_size_bytes: int = Field(default=0, ge=0)


class ParseErrorRecord(ContractModel):
    """A recoverable dataset or label parsing error with source context."""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    line_number: int | None = Field(default=None, ge=1)
    raw_line: str | None = None
    class_id: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    metrics: dict[str, JsonValue] = Field(default_factory=dict)


class DatasetManifest(ContractModel):
    """Parsed dataset inventory; it never implies source files were modified."""

    dataset_name: str = Field(min_length=1)
    source_archive: str = Field(min_length=1)
    images: list[ImageRecord] = Field(default_factory=list)
    annotations: list[AnnotationRecord] = Field(default_factory=list)
    class_names: dict[int, str] = Field(default_factory=dict)
    parse_errors: list[ParseErrorRecord] = Field(default_factory=list)
    unreadable_image_paths: list[str] = Field(default_factory=list)
    summary: DatasetSummary

    @field_validator("unreadable_image_paths")
    @classmethod
    def require_unique_unreadable_paths(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("unreadable image paths must be unique")
        if any(not path.strip() for path in value):
            raise ValueError("unreadable image paths must not be blank")
        return value

    @field_validator("class_names")
    @classmethod
    def validate_class_names(cls, value: dict[int, str]) -> dict[int, str]:
        if any(class_id < 0 for class_id in value):
            raise ValueError("class IDs must be non-negative")
        if any(not name.strip() for name in value.values()):
            raise ValueError("class names must not be blank")
        return value


class Issue(ContractModel):
    """One evidence-backed problem emitted by a deterministic check."""

    issue_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    code: str = Field(min_length=1)
    severity: Severity
    message: str = Field(min_length=1)
    relative_path: str | None = None
    image_id: str | None = None
    annotation_line: int | None = Field(default=None, ge=1)
    bbox: tuple[float, float, float, float] | None = None
    metrics: dict[str, JsonValue] = Field(default_factory=dict)
    suggested_action: str = Field(
        default="Review the source data and decide whether correction is appropriate.",
        min_length=1,
    )
    evidence: dict[str, JsonValue] = Field(default_factory=dict)


class DuplicateGroup(ContractModel):
    """A deterministic group of exact or perceptually similar images."""

    group_id: str = Field(min_length=1)
    kind: Literal["exact", "near"]
    image_ids: list[str] = Field(min_length=2)
    representative_image_id: str | None = None
    hamming_distance: int | None = Field(default=None, ge=0, le=64)
    pair_distances: dict[str, int] = Field(default_factory=dict)

    @field_validator("image_ids")
    @classmethod
    def require_unique_images(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("duplicate groups require unique image IDs")
        return value

    @model_validator(mode="after")
    def validate_representative(self) -> DuplicateGroup:
        if (
            self.representative_image_id is not None
            and self.representative_image_id not in self.image_ids
        ):
            raise ValueError("duplicate-group representative must be a group member")
        return self


class DistributionStats(ContractModel):
    """Class-frequency facts used for reporting and scoring."""

    total_annotations: int = Field(ge=0)
    class_counts: dict[int, int] = Field(default_factory=dict)
    class_image_counts: dict[int, int] = Field(default_factory=dict)
    class_percentages: dict[int, float] = Field(default_factory=dict)
    imbalance_ratio: float | None = Field(default=None, ge=1.0)
    imbalance_index: float | None = Field(default=None, ge=1.0)
    rare_class_ids: list[int] = Field(default_factory=list)
    missing_class_ids: list[int] = Field(default_factory=list)
    zero_instance_class_ids: list[int] = Field(default_factory=list)
    rare_class_threshold: float = Field(default=0.0, ge=0.0)

    @field_validator("class_counts")
    @classmethod
    def validate_counts(cls, value: dict[int, int]) -> dict[int, int]:
        if any(class_id < 0 or count < 0 for class_id, count in value.items()):
            raise ValueError("class IDs and counts must be non-negative")
        return value

    @field_validator("class_percentages")
    @classmethod
    def validate_percentages(cls, value: dict[int, float]) -> dict[int, float]:
        if any(class_id < 0 or not 0.0 <= share <= 1.0 for class_id, share in value.items()):
            raise ValueError("class percentages must be in [0, 1]")
        return value


class ScoreBreakdown(ContractModel):
    """One weighted, reproducible component of the health score."""

    component: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=100.0)
    weight: float = Field(gt=0.0, le=1.0)
    deductions: list[str] = Field(default_factory=list)


class HealthScore(ContractModel):
    """A heuristic dataset-health indicator, not a model-quality guarantee."""

    overall: float = Field(ge=0.0, le=100.0)
    grade: Literal["A", "B", "C", "D", "F"] = "F"
    penalties: dict[str, float] = Field(default_factory=dict)
    raw_ratios: dict[str, float] = Field(default_factory=dict)
    explanation: list[str] = Field(default_factory=list)
    breakdown: list[ScoreBreakdown] = Field(min_length=1)
    methodology_version: str = Field(default="1.0.0", min_length=1)
    profile_name: Literal["legacy-v1", "calibrated-v2"] = "legacy-v1"
    penalty_caps: dict[str, float] = Field(default_factory=dict)
    scoring_rules: dict[str, JsonValue] = Field(default_factory=dict)
    calibration_metadata: dict[str, JsonValue] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    disclaimer: str = Field(
        default=(
            "Heuristic data-quality indicator only; it is not a medical diagnosis, "
            "a model-accuracy prediction, or a substitute for expert review."
        ),
        min_length=1,
    )

    @field_validator("penalties")
    @classmethod
    def validate_penalties(cls, value: dict[str, float]) -> dict[str, float]:
        if any(penalty < 0.0 for penalty in value.values()):
            raise ValueError("health-score penalties must be non-negative")
        return value

    @field_validator("penalty_caps")
    @classmethod
    def validate_penalty_caps(cls, value: dict[str, float]) -> dict[str, float]:
        if any(cap < 0.0 or cap > 100.0 for cap in value.values()):
            raise ValueError("health-score penalty caps must be in [0, 100]")
        return value

    @field_validator("raw_ratios")
    @classmethod
    def validate_raw_ratios(cls, value: dict[str, float]) -> dict[str, float]:
        if any(not 0.0 <= ratio <= 1.0 for ratio in value.values()):
            raise ValueError("health-score raw ratios must be in [0, 1]")
        return value

    @model_validator(mode="after")
    def keep_grade_consistent_with_overall(self) -> HealthScore:
        if self.overall >= 90.0:
            expected = "A"
        elif self.overall >= 80.0:
            expected = "B"
        elif self.overall >= 70.0:
            expected = "C"
        elif self.overall >= 60.0:
            expected = "D"
        else:
            expected = "F"
        object.__setattr__(self, "grade", expected)
        return self


class PriorityFinding(ContractModel):
    """A diagnosis-layer prioritization backed by immutable issue IDs."""

    rank: int = Field(ge=1)
    title: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    severity: Severity
    issue_ids: list[str] = Field(default_factory=list)
    affected_count: int = Field(default=0, ge=0)
    score_penalty: float = Field(default=0.0, ge=0.0)
    inference: str | None = None
    needs_human_confirmation: bool = True


class RecommendedAction(ContractModel):
    """A proposed user action; it does not mutate the source dataset."""

    action_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    priority: int = Field(ge=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    related_issue_ids: list[str] = Field(default_factory=list)
    estimated_effort: Literal["low", "medium", "high"] = "medium"


class EvidenceClaim(ContractModel):
    """One structured fact, inference, or manual-confirmation claim."""

    claim_type: Literal[
        "dataset_count",
        "issue_count",
        "health_score",
        "score_penalty",
        "class_instance_count",
        "duplicate_group_count",
        "split_leakage_group_count",
        "repair_simulation",
        "qualitative",
    ]
    metric_name: str = Field(min_length=1, max_length=96)
    claimed_value: JsonValue
    source_tool: Literal[
        "get_dataset_summary",
        "get_issue_group",
        "get_representative_issues",
        "get_class_distribution",
        "get_score_component",
        "get_duplicate_summary",
        "get_split_leakage_summary",
        "get_repair_simulations",
    ]
    related_issue_ids: list[str] = Field(default_factory=list, max_length=20)
    classification: Literal["fact", "inference", "manual_confirmation"]


class Diagnosis(ContractModel):
    """Common output contract for deterministic and optional LLM diagnosis."""

    generated_by: Literal["deterministic", "llm"]
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    summary: str = Field(min_length=1)
    priority_findings: list[PriorityFinding] = Field(default_factory=list)
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
    evidence_claims: list[EvidenceClaim] = Field(default_factory=list, max_length=30)
    caveats: list[str] = Field(default_factory=list)


class RepairScenario(ContractModel):
    """One explicitly hypothetical, non-mutating repair selection."""

    scenario_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    selection_kind: Literal[
        "issue_ids",
        "issue_code",
        "duplicate_group",
        "exclude_unreadable",
        "fix_split_leakage",
    ]
    issue_ids: list[str] = Field(default_factory=list)
    issue_code: str | None = None
    duplicate_group_id: str | None = None
    suggested_action: str = Field(min_length=1)
    estimated_effort: Literal["low", "medium", "high"]
    assumptions: list[str] = Field(min_length=1)
    requires_human_confirmation: bool = True

    @model_validator(mode="after")
    def validate_selector(self) -> RepairScenario:
        if self.selection_kind == "issue_ids" and not self.issue_ids:
            raise ValueError("issue_ids scenarios require at least one issue ID")
        if self.selection_kind == "issue_code" and not self.issue_code:
            raise ValueError("issue_code scenarios require an issue code")
        if self.selection_kind == "duplicate_group" and not self.duplicate_group_id:
            raise ValueError(
                "duplicate_group scenarios require a duplicate group ID"
            )
        return self


class RepairImpact(ContractModel):
    """Score delta under one stated repair assumption."""

    scenario: RepairScenario
    original_score: float = Field(ge=0.0, le=100.0)
    simulated_score: float = Field(ge=0.0, le=100.0)
    score_delta: float = Field(ge=-100.0, le=100.0)
    affected_issue_ids: list[str] = Field(default_factory=list)
    affected_issue_count: int = Field(ge=0)
    affected_duplicate_group_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(min_length=1)
    caveats: list[str] = Field(min_length=1)
    source_data_modified: Literal[False] = False


class RepairSimulationReport(ContractModel):
    """Deterministic score what-if results; never evidence of an applied repair."""

    methodology_version: str = Field(default="1.0.0", min_length=1)
    profile_name: Literal["legacy-v1", "calibrated-v2"]
    impacts: list[RepairImpact] = Field(default_factory=list, max_length=5)
    disclaimer: str = Field(
        default=(
            "仅用于假设性的健康分预演。没有修改任何源文件，结果也不能预测 "
            "mAP、训练质量或业务效果。"
        ),
        min_length=1,
    )


class AuditReport(ContractModel):
    """Versioned aggregate used by JSON, HTML, and the Issue Explorer."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    report_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    generated_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    manifest: DatasetManifest
    issues: list[Issue] = Field(default_factory=list)
    duplicate_groups: list[DuplicateGroup] = Field(default_factory=list)
    distribution: DistributionStats
    health_score: HealthScore
    threshold_snapshot: dict[str, JsonValue] = Field(default_factory=dict)
    repair_simulation: RepairSimulationReport | None = None
    knowledge_guidance: KnowledgeGuidanceContext | None = None
    diagnosis: Diagnosis | None = None
    diagnosis_failure_stage: str | None = Field(default=None, max_length=64)
    diagnosis_mode: Literal[
        "not_run",
        "deterministic_fallback",
        "one_shot",
        "evidence_query",
    ] = "not_run"

    @field_validator("generated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value
