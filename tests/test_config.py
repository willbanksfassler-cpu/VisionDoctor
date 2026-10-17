"""Tests for centralized VisionDoctor configuration."""

import pytest
from pydantic import ValidationError

from vision_doctor.config import LLMConfig, Settings


def test_settings_have_safe_offline_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.upload.max_archive_size_mb > 0
    assert settings.upload.max_extracted_size_mb >= settings.upload.max_archive_size_mb
    assert settings.image_quality.dark_mean_threshold < 128
    assert settings.image_quality.bright_mean_threshold > 128
    assert 0 <= settings.duplicate_detection.near_duplicate_hamming_threshold <= 64
    assert settings.llm.enabled is False
    assert settings.llm.api_key is None
    assert settings.live_api_test is False


def test_nested_environment_variables_override_defaults(monkeypatch) -> None:
    monkeypatch.setenv("VISION_DOCTOR_UPLOAD__MAX_ARCHIVE_SIZE_MB", "123")
    monkeypatch.setenv("VISION_DOCTOR_IMAGE_QUALITY__MIN_WIDTH", "96")
    monkeypatch.setenv(
        "VISION_DOCTOR_DUPLICATE_DETECTION__NEAR_DUPLICATE_HAMMING_THRESHOLD",
        "7",
    )
    monkeypatch.setenv("VISION_DOCTOR_LLM__ENABLED", "true")
    monkeypatch.setenv("VISION_DOCTOR_LLM__MODEL", "placeholder-model")
    monkeypatch.setenv("VISION_DOCTOR_LIVE_API_TEST", "true")

    settings = Settings(_env_file=None)

    assert settings.upload.max_archive_size_mb == 123
    assert settings.image_quality.min_width == 96
    assert settings.duplicate_detection.near_duplicate_hamming_threshold == 7
    assert settings.llm.enabled is True
    assert settings.llm.model == "placeholder-model"
    assert settings.live_api_test is True


def test_deepseek_environment_uses_official_default_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("VISION_DOCTOR_LLM__PROVIDER", "deepseek")
    monkeypatch.setenv("VISION_DOCTOR_LLM__MODEL", "deepseek-flash")

    settings = Settings(_env_file=None)

    assert settings.llm.provider == "deepseek"
    assert settings.llm.model == "deepseek-flash"
    assert settings.llm.base_url == "https://api.deepseek.com"


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "http://api.deepseek.com",
        "https://example.com",
        "https://api.deepseek.com.evil.example",
        "https://user:secret@api.deepseek.com",
        "https://api.deepseek.com/v1",
    ],
)
def test_deepseek_rejects_unsafe_or_non_official_urls(unsafe_url: str) -> None:
    with pytest.raises(ValidationError, match="base_url"):
        LLMConfig(provider="deepseek", base_url=unsafe_url)
