"""Central configuration for safety limits and audit thresholds."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, JsonValue, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from vision_doctor.models import KnowledgeProfile


class UploadLimits(BaseModel):
    """Resource limits applied before and during archive extraction."""

    max_archive_size_mb: int = Field(default=200, gt=0)
    max_entries: int = Field(default=20_000, gt=0)
    max_single_file_size_mb: int = Field(default=50, gt=0)
    max_extracted_size_mb: int = Field(default=1_000, gt=0)
    max_compression_ratio: float = Field(default=100.0, gt=1.0)
    allowed_image_extensions: frozenset[str] = frozenset(
        {".bmp", ".jpeg", ".jpg", ".png", ".webp"}
    )


class ImageQualityThresholds(BaseModel):
    """Explainable defaults for image-level quality checks."""

    mode: Literal["fixed", "adaptive"] = "fixed"
    min_width: int = Field(default=320, gt=0)
    min_height: int = Field(default=320, gt=0)
    blur_variance_threshold: float = Field(default=80.0, ge=0.0)
    dark_mean_threshold: float = Field(default=45.0, ge=0.0, le=255.0)
    bright_mean_threshold: float = Field(default=210.0, ge=0.0, le=255.0)
    adaptive_min_samples: int = Field(default=12, ge=5)
    adaptive_mad_multiplier: float = Field(default=3.5, gt=0.0, le=10.0)
    adaptive_blur_min: float = Field(default=20.0, ge=0.0)
    adaptive_blur_max: float = Field(default=200.0, gt=0.0)
    adaptive_dark_min: float = Field(default=15.0, ge=0.0, le=255.0)
    adaptive_dark_max: float = Field(default=80.0, ge=0.0, le=255.0)
    adaptive_bright_min: float = Field(default=175.0, ge=0.0, le=255.0)
    adaptive_bright_max: float = Field(default=245.0, ge=0.0, le=255.0)
    adaptive_dimension_min: float = Field(default=128.0, gt=0.0)
    adaptive_dimension_max: float = Field(default=1024.0, gt=0.0)

    @model_validator(mode="after")
    def validate_adaptive_bounds(self) -> ImageQualityThresholds:
        bounds = (
            (self.adaptive_blur_min, self.adaptive_blur_max, "blur"),
            (self.adaptive_dark_min, self.adaptive_dark_max, "dark"),
            (self.adaptive_bright_min, self.adaptive_bright_max, "bright"),
            (
                self.adaptive_dimension_min,
                self.adaptive_dimension_max,
                "dimension",
            ),
        )
        for lower, upper, name in bounds:
            if lower >= upper:
                raise ValueError(f"adaptive {name} bounds must be increasing")
        if self.adaptive_dark_max >= self.adaptive_bright_min:
            raise ValueError("adaptive dark and bright bounds must not overlap")
        return self


class DuplicateDetectionConfig(BaseModel):
    """Hash settings for exact and near-duplicate grouping."""

    exact_hash_algorithm: Literal["sha256"] = "sha256"
    perceptual_hash_size: int = Field(default=8, ge=4, le=32)
    near_duplicate_hamming_threshold: int = Field(default=4, ge=0, le=64)
    max_images_for_pairwise: int = Field(default=2_000, ge=2)


class BBoxOutlierConfig(BaseModel):
    """Robust, class-conditional bounding-box outlier settings."""

    enabled: bool = True
    min_samples_per_class: int = Field(default=10, ge=5)
    robust_z_threshold: float = Field(default=3.5, gt=0.0, le=10.0)
    zero_dispersion_log_ratio_threshold: float = Field(
        default=1.38629436112,
        gt=0.0,
    )


class ScoringConfig(BaseModel):
    """Health-score profile selection with an explicit calibration gate."""

    profile_name: Literal["legacy-v1", "calibrated-v2"] = "legacy-v1"
    calibrated_v2_enabled: bool = False
    calibrated_v2_penalty_caps: dict[str, float] = Field(
        default_factory=lambda: {
            "structural": 27.0,
            "bbox": 23.0,
            "image": 20.0,
            "duplicates": 12.0,
            "distribution": 18.0,
        }
    )
    calibration_metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_accepted_calibration(self) -> ScoringConfig:
        if self.profile_name == "legacy-v1":
            return self
        accepted = self.calibration_metadata.get("acceptance_passed") is True
        benchmark_profile = self.calibration_metadata.get("benchmark_profile")
        monotonic = self.calibration_metadata.get("monotonicity_passed") is True
        schema = self.calibration_metadata.get("benchmark_schema_version")
        if (
            not self.calibrated_v2_enabled
            or not accepted
            or benchmark_profile not in {"standard", "scale"}
            or not monotonic
            or schema != "1.0.0"
        ):
            raise ValueError(
                "calibrated-v2 requires explicit enablement and an accepted "
                "standard/scale benchmark with schema 1.0.0 and monotonicity proof"
            )
        return self


class LLMConfig(BaseModel):
    """Optional LLM configuration; disabled and credential-free by default."""

    enabled: bool = False
    provider: Literal["openai", "deepseek"] = "openai"
    model: str | None = None
    api_key: SecretStr | None = None
    base_url: str | None = None
    timeout_seconds: float = Field(default=30.0, gt=0.0, le=300.0)
    max_retries: int = Field(default=2, ge=0, le=5)
    max_representative_evidence: int = Field(default=5, ge=1, le=20)
    evidence_query_enabled: bool = True
    max_tool_rounds: int = Field(default=3, ge=1, le=3)
    max_tool_calls_per_round: int = Field(default=3, ge=1, le=5)
    max_tool_result_items: int = Field(default=10, ge=1, le=20)
    max_tool_result_bytes: int = Field(default=8_000, ge=512, le=32_000)
    max_total_evidence_bytes: int = Field(
        default=24_000,
        ge=1_024,
        le=100_000,
    )

    @model_validator(mode="after")
    def validate_provider_endpoint(self) -> LLMConfig:
        """Apply safe provider defaults and reject credential exfiltration URLs."""

        if self.base_url is None:
            if self.provider == "deepseek":
                object.__setattr__(self, "base_url", "https://api.deepseek.com")
            return self

        parsed = urlsplit(self.base_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("LLM base_url must be a credential-free HTTPS origin")

        if self.provider == "deepseek":
            is_official_origin = (
                parsed.hostname.lower() == "api.deepseek.com"
                and parsed.port in {None, 443}
                and parsed.path.rstrip("/") == ""
            )
            if not is_official_origin:
                raise ValueError(
                    "DeepSeek base_url must be the official https://api.deepseek.com origin"
                )
            object.__setattr__(self, "base_url", "https://api.deepseek.com")
        return self


class KnowledgeConfig(BaseModel):
    """Bounded selection for local, advisory scenario guidance."""

    profile: KnowledgeProfile = KnowledgeProfile.GENERIC
    max_guidance_items: int = Field(default=5, ge=1, le=10)
    max_questions: int = Field(default=5, ge=1, le=10)


class Settings(BaseSettings):
    """Application settings with ``VISION_DOCTOR_`` environment overrides."""

    model_config = SettingsConfigDict(
        env_prefix="VISION_DOCTOR_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        case_sensitive=False,
        extra="ignore",
    )

    upload: UploadLimits = Field(default_factory=UploadLimits)
    image_quality: ImageQualityThresholds = Field(
        default_factory=ImageQualityThresholds
    )
    duplicate_detection: DuplicateDetectionConfig = Field(
        default_factory=DuplicateDetectionConfig
    )
    bbox_outliers: BBoxOutlierConfig = Field(default_factory=BBoxOutlierConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    knowledge: KnowledgeConfig = Field(default_factory=KnowledgeConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    live_api_test: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one validated settings object for the current process."""

    return Settings()
