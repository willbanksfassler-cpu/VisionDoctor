"""Validated optional LLM path for the single Dataset Doctor."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from vision_doctor.agent.evidence_tools import (
    EvidenceLimitError,
    EvidenceQueryService,
    EvidenceToolArgumentsError,
    UnknownEvidenceToolError,
)
from vision_doctor.agent.fallback import build_fallback_diagnosis
from vision_doctor.agent.prompts import build_evidence_query_prompts, build_prompts
from vision_doctor.agent.validator import (
    FactValidationCode,
    validate_diagnosis_facts,
)
from vision_doctor.config import LLMConfig
from vision_doctor.models import AuditReport, Diagnosis


@runtime_checkable
class DatasetDoctorClient(Protocol):
    """Small injectable one-shot interface retained for compatibility."""

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
        timeout_seconds: float,
    ) -> str: ...


class EvidenceToolCall(BaseModel):
    """Normalized provider tool request without executable content."""

    model_config = ConfigDict(extra="forbid")

    call_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    arguments_json: str = Field(min_length=1, max_length=16_000)


class EvidenceToolTurn(BaseModel):
    """One provider turn containing either tool calls or final JSON text."""

    model_config = ConfigDict(extra="forbid")

    content: str | None = None
    tool_calls: list[EvidenceToolCall] = Field(default_factory=list, max_length=10)


@runtime_checkable
class EvidenceQueryDatasetDoctorClient(Protocol):
    """Optional interface for providers that support function tools."""

    def complete_tool_turn(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
        timeout_seconds: float,
    ) -> EvidenceToolTurn: ...


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
    UNKNOWN_TOOL = "unknown_tool"
    TOOL_ARGUMENT_ERROR = "tool_argument_error"
    TOOL_PROTOCOL_ERROR = "tool_protocol_error"
    TOOL_ROUND_LIMIT = "tool_round_limit"
    EVIDENCE_LIMIT_EXCEEDED = "evidence_limit_exceeded"
    FACT_CLAIM_MISMATCH = "fact_claim_mismatch"
    SEVERITY_MISMATCH = "severity_mismatch"
    CRITICAL_ISSUE_OMITTED = "critical_issue_omitted"
    PROHIBITED_PERFORMANCE_PROMISE = "prohibited_performance_promise"
    DATA_MODIFICATION_CLAIM = "data_modification_claim"
    UNKNOWN_ERROR = "unknown_error"


@dataclass(frozen=True)
class DiagnosisOutcome:
    """Validated diagnosis plus a sanitized provider/validation outcome."""

    diagnosis: Diagnosis
    failure_stage: LLMFailureStage | None
    live_api_verified: bool
    execution_mode: Literal[
        "deterministic_fallback",
        "one_shot",
        "evidence_query",
    ] = "deterministic_fallback"


class EmptyProviderResponseError(Exception):
    """Internal marker for a provider response without usable text."""


class ToolProtocolError(Exception):
    """Internal marker for malformed provider tool-call envelopes."""


class AgentWorkflowError(Exception):
    """Internal sanitized failure carrying no provider or evidence text."""

    def __init__(self, stage: LLMFailureStage) -> None:
        self.stage = stage
        super().__init__(stage.value)


def _attribute(value: object, name: str, default: object = None) -> object:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


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

    def _sdk(self, timeout_seconds: float) -> Any:
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
        return factory(**client_options)

    def _base_request(self, model: str) -> dict[str, object]:
        request: dict[str, object] = {
            "model": model,
            "response_format": {"type": "json_object"},
            "stream": False,
            "max_tokens": self._max_output_tokens,
        }
        if self._provider == "deepseek":
            request["extra_body"] = {"thinking": {"type": "disabled"}}
        return request

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
        timeout_seconds: float,
    ) -> str:
        request_options = self._base_request(model)
        request_options["messages"] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        response = self._sdk(timeout_seconds).chat.completions.create(
            **request_options
        )
        content = _attribute(_attribute(response.choices[0], "message"), "content")
        if not isinstance(content, str) or not content.strip():
            raise EmptyProviderResponseError
        return content

    def complete_tool_turn(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
        timeout_seconds: float,
    ) -> EvidenceToolTurn:
        request_options = self._base_request(model)
        request_options.update(
            {
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
            }
        )
        response = self._sdk(timeout_seconds).chat.completions.create(
            **request_options
        )
        message = _attribute(response.choices[0], "message")
        content = _attribute(message, "content")
        raw_calls = _attribute(message, "tool_calls", []) or []
        if content is not None and not isinstance(content, str):
            raise ToolProtocolError
        calls: list[EvidenceToolCall] = []
        for raw_call in raw_calls:
            function = _attribute(raw_call, "function")
            call_id = _attribute(raw_call, "id")
            name = _attribute(function, "name")
            arguments = _attribute(function, "arguments")
            if not all(isinstance(item, str) and item for item in (call_id, name, arguments)):
                raise ToolProtocolError
            calls.append(
                EvidenceToolCall(
                    call_id=call_id,
                    name=name,
                    arguments_json=arguments,
                )
            )
        if not calls and (not isinstance(content, str) or not content.strip()):
            raise EmptyProviderResponseError
        return EvidenceToolTurn(content=content, tool_calls=calls)


def _fallback_outcome(
    report: AuditReport,
    failure_stage: LLMFailureStage,
) -> DiagnosisOutcome:
    return DiagnosisOutcome(
        diagnosis=build_fallback_diagnosis(report),
        failure_stage=failure_stage,
        live_api_verified=False,
        execution_mode="deterministic_fallback",
    )


def _classify_provider_error(error: Exception) -> LLMFailureStage:
    """Classify by exception type only; never inspect or retain its message."""

    type_names = {error_type.__name__ for error_type in type(error).__mro__}
    if isinstance(error, EmptyProviderResponseError):
        return LLMFailureStage.EMPTY_RESPONSE
    if isinstance(error, ToolProtocolError):
        return LLMFailureStage.TOOL_PROTOCOL_ERROR
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


def _assistant_tool_message(turn: EvidenceToolTurn) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": turn.content,
        "tool_calls": [
            {
                "id": call.call_id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": call.arguments_json,
                },
            }
            for call in turn.tool_calls
        ],
    }


def _run_evidence_query_loop(
    report: AuditReport,
    config: LLMConfig,
    client: EvidenceQueryDatasetDoctorClient,
) -> str:
    service = EvidenceQueryService(
        report,
        max_items=config.max_tool_result_items,
        max_result_bytes=config.max_tool_result_bytes,
    )
    try:
        initial_evidence = service.execute("get_dataset_summary", {})
    except EvidenceLimitError:
        raise AgentWorkflowError(LLMFailureStage.EVIDENCE_LIMIT_EXCEEDED) from None
    evidence_bytes = len(initial_evidence.encode("utf-8"))
    if evidence_bytes > config.max_total_evidence_bytes:
        raise AgentWorkflowError(LLMFailureStage.EVIDENCE_LIMIT_EXCEEDED)
    system_prompt, user_prompt = build_evidence_query_prompts(initial_evidence)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    tools = service.tool_definitions()
    completed_tool_rounds = 0

    while True:
        raw_turn = client.complete_tool_turn(
            messages=messages,
            tools=tools,
            model=config.model or "",
            timeout_seconds=config.timeout_seconds,
        )
        try:
            turn = EvidenceToolTurn.model_validate(raw_turn)
        except ValidationError:
            raise AgentWorkflowError(LLMFailureStage.TOOL_PROTOCOL_ERROR) from None
        if not turn.tool_calls:
            if not isinstance(turn.content, str) or not turn.content.strip():
                raise AgentWorkflowError(LLMFailureStage.EMPTY_RESPONSE)
            return turn.content
        if completed_tool_rounds >= config.max_tool_rounds:
            raise AgentWorkflowError(LLMFailureStage.TOOL_ROUND_LIMIT)
        if len(turn.tool_calls) > config.max_tool_calls_per_round:
            raise AgentWorkflowError(LLMFailureStage.TOOL_PROTOCOL_ERROR)
        call_ids = [call.call_id for call in turn.tool_calls]
        if len(set(call_ids)) != len(call_ids):
            raise AgentWorkflowError(LLMFailureStage.TOOL_PROTOCOL_ERROR)

        messages.append(_assistant_tool_message(turn))
        for call in turn.tool_calls:
            try:
                result = service.execute_json_arguments(
                    call.name,
                    call.arguments_json,
                )
            except UnknownEvidenceToolError:
                raise AgentWorkflowError(LLMFailureStage.UNKNOWN_TOOL) from None
            except EvidenceToolArgumentsError:
                raise AgentWorkflowError(LLMFailureStage.TOOL_ARGUMENT_ERROR) from None
            except EvidenceLimitError:
                raise AgentWorkflowError(
                    LLMFailureStage.EVIDENCE_LIMIT_EXCEEDED
                ) from None
            evidence_bytes += len(result.encode("utf-8"))
            if evidence_bytes > config.max_total_evidence_bytes:
                raise AgentWorkflowError(
                    LLMFailureStage.EVIDENCE_LIMIT_EXCEEDED
                )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.call_id,
                    "name": call.name,
                    "content": result,
                }
            )
        completed_tool_rounds += 1


_VALIDATION_STAGE = {
    FactValidationCode.GENERATED_BY_MISMATCH: (
        LLMFailureStage.GENERATED_BY_MISMATCH
    ),
    FactValidationCode.UNKNOWN_ISSUE_REFERENCE: (
        LLMFailureStage.UNKNOWN_ISSUE_REFERENCE
    ),
    FactValidationCode.CLAIM_SOURCE_MISMATCH: LLMFailureStage.FACT_CLAIM_MISMATCH,
    FactValidationCode.CLAIM_VALUE_MISMATCH: LLMFailureStage.FACT_CLAIM_MISMATCH,
    FactValidationCode.SEVERITY_MISMATCH: LLMFailureStage.SEVERITY_MISMATCH,
    FactValidationCode.CRITICAL_ISSUE_OMITTED: (
        LLMFailureStage.CRITICAL_ISSUE_OMITTED
    ),
    FactValidationCode.PROHIBITED_PERFORMANCE_PROMISE: (
        LLMFailureStage.PROHIBITED_PERFORMANCE_PROMISE
    ),
    FactValidationCode.DATA_MODIFICATION_CLAIM: (
        LLMFailureStage.DATA_MODIFICATION_CLAIM
    ),
}

_VALIDATION_PRIORITY = (
    FactValidationCode.GENERATED_BY_MISMATCH,
    FactValidationCode.UNKNOWN_ISSUE_REFERENCE,
    FactValidationCode.CLAIM_SOURCE_MISMATCH,
    FactValidationCode.CLAIM_VALUE_MISMATCH,
    FactValidationCode.SEVERITY_MISMATCH,
    FactValidationCode.CRITICAL_ISSUE_OMITTED,
    FactValidationCode.PROHIBITED_PERFORMANCE_PROMISE,
    FactValidationCode.DATA_MODIFICATION_CLAIM,
)


def _first_validation_stage(failures: list[FactValidationCode]) -> LLMFailureStage:
    found = set(failures)
    return next(
        _VALIDATION_STAGE[code]
        for code in _VALIDATION_PRIORITY
        if code in found
    )


def diagnose_report_with_status(
    report: AuditReport,
    config: LLMConfig,
    *,
    client: DatasetDoctorClient | EvidenceQueryDatasetDoctorClient | None = None,
) -> DiagnosisOutcome:
    """Return a diagnosis and a sanitized reason for any deterministic fallback."""

    key = config.api_key.get_secret_value() if config.api_key is not None else None
    if not config.enabled:
        return _fallback_outcome(report, LLMFailureStage.LLM_DISABLED)
    if not key:
        return _fallback_outcome(report, LLMFailureStage.CREDENTIALS_MISSING)
    if not config.model:
        return _fallback_outcome(report, LLMFailureStage.MODEL_MISSING)

    execution_mode: Literal["one_shot", "evidence_query"] = "one_shot"
    try:
        active_client = client or OpenAICompatibleDatasetDoctorClient(
            key,
            provider=config.provider,
            base_url=config.base_url,
            max_retries=config.max_retries,
        )
        if config.evidence_query_enabled and isinstance(
            active_client,
            EvidenceQueryDatasetDoctorClient,
        ):
            execution_mode = "evidence_query"
            raw_response = _run_evidence_query_loop(
                report,
                config,
                active_client,
            )
        elif isinstance(active_client, DatasetDoctorClient):
            system_prompt, user_prompt = build_prompts(
                report,
                max_representative_evidence=(
                    config.max_representative_evidence
                ),
            )
            raw_response = active_client.complete(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=config.model,
                timeout_seconds=config.timeout_seconds,
            )
        else:
            return _fallback_outcome(
                report,
                LLMFailureStage.TOOL_PROTOCOL_ERROR,
            )
    except AgentWorkflowError as error:
        return _fallback_outcome(report, error.stage)
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
    validation = validate_diagnosis_facts(diagnosis, report)
    if not validation.valid:
        return _fallback_outcome(
            report,
            _first_validation_stage(validation.failures),
        )
    return DiagnosisOutcome(
        diagnosis=diagnosis,
        failure_stage=None,
        live_api_verified=True,
        execution_mode=execution_mode,
    )


def diagnose_report(
    report: AuditReport,
    config: LLMConfig,
    *,
    client: DatasetDoctorClient | EvidenceQueryDatasetDoctorClient | None = None,
) -> Diagnosis:
    """Use validated LLM JSON when possible; otherwise always return fallback."""

    return diagnose_report_with_status(report, config, client=client).diagnosis
