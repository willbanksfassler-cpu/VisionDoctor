"""Validated optional LLM path for the single Dataset Doctor."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import ValidationError

from vision_doctor.agent.fallback import build_fallback_diagnosis
from vision_doctor.agent.prompts import build_prompts
from vision_doctor.config import LLMConfig
from vision_doctor.models import AuditReport, Diagnosis


@runtime_checkable
class DatasetDoctorClient(Protocol):
    """Small injectable interface used by fake clients in tests."""

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
        timeout_seconds: float,
    ) -> str: ...


class LLMFailureStage(str, Enum):
    """Non-sensitive reason why an LLM diagnosis was not accepted."""

    LLM_DISABLED = "llm_disabled"
    CREDENTIALS_MISSING = "credentials_missing"
    MODEL_MISSING = "model_missing"
    SDK_UNAVAILABLE = "sdk_unavailable"
    REQUEST_TIMEOUT = "request_timeout"
    AUTHENTICATION_ERROR = "authentication_error"
    RATE_LIMIT_OR_BALANCE_ERROR = "rate_limit_or_balance_error"
    CONNECTION_ERROR = "connection_error"
    PROVIDER_API_ERROR = "provider_api_error"
    EMPTY_RESPONSE = "empty_response"
    INVALID_JSON = "invalid_json"
    DIAGNOSIS_SCHEMA_ERROR = "diagnosis_schema_error"
    GENERATED_BY_MISMATCH = "generated_by_mismatch"
    UNKNOWN_ISSUE_REFERENCE = "unknown_issue_reference"
    UNKNOWN_ERROR = "unknown_error"


@dataclass(frozen=True)
class DiagnosisOutcome:
    """Validated diagnosis plus a sanitized provider/validation outcome."""

    diagnosis: Diagnosis
    failure_stage: LLMFailureStage | None
    live_api_verified: bool


class EmptyProviderResponseError(Exception):
    """Internal marker for a provider response without usable text."""


class OpenAICompatibleDatasetDoctorClient:
    """Lazy OpenAI-compatible adapter for OpenAI and official DeepSeek APIs."""

    def __init__(
        self,
        api_key: str,
        *,
        provider: str,
        base_url: str | None,
        max_retries: int,
        max_output_tokens: int = 4_000,
        sdk_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._api_key = api_key
        self._provider = provider
        self._base_url = base_url
        self._max_retries = max_retries
        self._max_output_tokens = max_output_tokens
        self._sdk_factory = sdk_factory

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
        timeout_seconds: float,
    ) -> str:
        factory = self._sdk_factory
        if factory is None:
            from openai import OpenAI

            factory = OpenAI

        client_options: dict[str, object] = {
            "api_key": self._api_key,
            "timeout": timeout_seconds,
            "max_retries": self._max_retries,
        }
        if self._base_url is not None:
            client_options["base_url"] = self._base_url
        sdk = factory(**client_options)

        request_options: dict[str, object] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "stream": False,
            "max_tokens": self._max_output_tokens,
        }
        if self._provider == "deepseek":
            request_options["extra_body"] = {"thinking": {"type": "disabled"}}
        response = sdk.chat.completions.create(
            **request_options,
        )
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise EmptyProviderResponseError
        return content


def _references_known_evidence(diagnosis: Diagnosis, report: AuditReport) -> bool:
    known_ids = {issue.issue_id for issue in report.issues}
    referenced = {
        issue_id
        for finding in diagnosis.priority_findings
        for issue_id in finding.issue_ids
    }
    referenced.update(
        issue_id
        for action in diagnosis.recommended_actions
        for issue_id in action.related_issue_ids
    )
    return referenced <= known_ids


def _fallback_outcome(
    report: AuditReport,
    failure_stage: LLMFailureStage,
) -> DiagnosisOutcome:
    return DiagnosisOutcome(
        diagnosis=build_fallback_diagnosis(report),
        failure_stage=failure_stage,
        live_api_verified=False,
    )


def _classify_provider_error(error: Exception) -> LLMFailureStage:
    """Classify by exception type only; never inspect or retain its message."""

    type_names = {error_type.__name__ for error_type in type(error).__mro__}
    if isinstance(error, EmptyProviderResponseError):
        return LLMFailureStage.EMPTY_RESPONSE
    if isinstance(error, ModuleNotFoundError):
        return LLMFailureStage.SDK_UNAVAILABLE
    if isinstance(error, TimeoutError) or "APITimeoutError" in type_names:
        return LLMFailureStage.REQUEST_TIMEOUT
    if "AuthenticationError" in type_names:
        return LLMFailureStage.AUTHENTICATION_ERROR
    if "RateLimitError" in type_names:
        return LLMFailureStage.RATE_LIMIT_OR_BALANCE_ERROR
    if "APIConnectionError" in type_names:
        return LLMFailureStage.CONNECTION_ERROR
    if "APIStatusError" in type_names:
        return LLMFailureStage.PROVIDER_API_ERROR
    return LLMFailureStage.UNKNOWN_ERROR


def diagnose_report_with_status(
    report: AuditReport,
    config: LLMConfig,
    *,
    client: DatasetDoctorClient | None = None,
) -> DiagnosisOutcome:
    """Return a diagnosis and a sanitized reason for any deterministic fallback."""

    key = config.api_key.get_secret_value() if config.api_key is not None else None
    if not config.enabled:
        return _fallback_outcome(report, LLMFailureStage.LLM_DISABLED)
    if not key:
        return _fallback_outcome(report, LLMFailureStage.CREDENTIALS_MISSING)
    if not config.model:
        return _fallback_outcome(report, LLMFailureStage.MODEL_MISSING)

    try:
        active_client = client or OpenAICompatibleDatasetDoctorClient(
            key,
            provider=config.provider,
            base_url=config.base_url,
            max_retries=config.max_retries,
        )
        system_prompt, user_prompt = build_prompts(
            report,
            max_representative_evidence=config.max_representative_evidence,
        )
        raw_response = active_client.complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=config.model,
            timeout_seconds=config.timeout_seconds,
        )
    except Exception as error:  # noqa: BLE001 - all provider failures must fall back
        return _fallback_outcome(report, _classify_provider_error(error))

    if not isinstance(raw_response, str) or not raw_response.strip():
        return _fallback_outcome(report, LLMFailureStage.EMPTY_RESPONSE)
    try:
        payload = json.loads(raw_response)
    except json.JSONDecodeError:
        return _fallback_outcome(report, LLMFailureStage.INVALID_JSON)
    try:
        diagnosis = Diagnosis.model_validate(payload)
    except ValidationError:
        return _fallback_outcome(report, LLMFailureStage.DIAGNOSIS_SCHEMA_ERROR)
    if diagnosis.generated_by != "llm":
        return _fallback_outcome(report, LLMFailureStage.GENERATED_BY_MISMATCH)
    if not _references_known_evidence(diagnosis, report):
        return _fallback_outcome(report, LLMFailureStage.UNKNOWN_ISSUE_REFERENCE)
    return DiagnosisOutcome(
        diagnosis=diagnosis,
        failure_stage=None,
        live_api_verified=True,
    )


def diagnose_report(
    report: AuditReport,
    config: LLMConfig,
    *,
    client: DatasetDoctorClient | None = None,
) -> Diagnosis:
    """Use validated LLM JSON when possible; otherwise always return fallback."""

    return diagnose_report_with_status(report, config, client=client).diagnosis
