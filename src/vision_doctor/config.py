"""Central configuration for safety limits and audit thresholds."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    min_width: int = Field(default=320, gt=0)
    min_height: int = Field(default=320, gt=0)
    blur_variance_threshold: float = Field(default=80.0, ge=0.0)
    dark_mean_threshold: float = Field(default=45.0, ge=0.0, le=255.0)
    bright_mean_threshold: float = Field(default=210.0, ge=0.0, le=255.0)


class DuplicateDetectionConfig(BaseModel):
    """Hash settings for exact and near-duplicate grouping."""

    exact_hash_algorithm: Literal["sha256"] = "sha256"
    perceptual_hash_size: int = Field(default=8, ge=4, le=32)
    near_duplicate_hamming_threshold: int = Field(default=4, ge=0, le=64)
    max_images_for_pairwise: int = Field(default=2_000, ge=2)


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
    llm: LLMConfig = Field(default_factory=LLMConfig)
    live_api_test: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one validated settings object for the current process."""

    return Settings()
