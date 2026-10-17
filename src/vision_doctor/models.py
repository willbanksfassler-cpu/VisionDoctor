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


class Diagnosis(ContractModel):
    """Common output contract for deterministic and optional LLM diagnosis."""

    generated_by: Literal["deterministic", "llm"]
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    summary: str = Field(min_length=1)
    priority_findings: list[PriorityFinding] = Field(default_factory=list)
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


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
    diagnosis: Diagnosis | None = None

    @field_validator("generated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value
