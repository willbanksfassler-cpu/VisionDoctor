"""Tests for constrained prompts, schema validation, and LLM fallback behavior."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import vision_doctor.agent.client as client_module
from scripts.generate_demo_dataset import generate_demo_zip
from vision_doctor.agent.client import (
    DatasetDoctorClient,
    DiagnosisOutcome,
    EvidenceToolCall,
    EvidenceToolTurn,
    LLMFailureStage,
    OpenAICompatibleDatasetDoctorClient,
    diagnose_report,
    diagnose_report_with_status,
)
from vision_doctor.agent.prompts import build_agent_payload, build_prompts
from vision_doctor.config import LLMConfig
from vision_doctor.pipeline import run_pipeline


class FakeClient:
    def __init__(self, response: str | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
        timeout_seconds: float,
    ) -> str:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "model": model,
                "timeout_seconds": timeout_seconds,
            }
        )
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeToolClient:
    def __init__(self, turns: list[EvidenceToolTurn | dict[str, object]]) -> None:
        self.turns = list(turns)
        self.calls: list[dict[str, object]] = []

    def complete_tool_turn(
        self,
        *,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
        model: str,
        timeout_seconds: float,
    ) -> EvidenceToolTurn | dict[str, object]:
        self.calls.append(
            {
                "messages": messages,
                "tools": tools,
                "model": model,
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.turns.pop(0)


def _report(tmp_path: Path):
    archive = generate_demo_zip(tmp_path / "demo.zip")
    return run_pipeline(archive, temp_root=tmp_path)


def _enabled_config(secret: str = "test-secret") -> LLMConfig:
    return LLMConfig(
        enabled=True,
        model="fake-model",
        api_key=secret,
        timeout_seconds=1,
    )


def _valid_llm_json() -> str:
    return json.dumps(
        {
            "generated_by": "llm",
            "risk_level": "medium",
            "summary": "Evidence indicates several dataset risks requiring review.",
            "priority_findings": [],
            "recommended_actions": [],
            "caveats": ["No model-performance improvement is guaranteed."],
        }
    )


def test_valid_llm_json_is_accepted_and_prompt_is_minimized(tmp_path: Path) -> None:
    report = _report(tmp_path)
    fake = FakeClient(_valid_llm_json())

    outcome = diagnose_report_with_status(report, _enabled_config(), client=fake)
    diagnosis = outcome.diagnosis

    assert diagnosis.generated_by == "llm"
    assert outcome.failure_stage is None
    assert outcome.live_api_verified is True
    assert outcome.execution_mode == "one_shot"
    assert len(fake.calls) == 1
    call = fake.calls[0]
    system_prompt = str(call["system_prompt"])
    assert "Never invent counts" in system_prompt
    assert "mAP" in system_prompt
    assert "negative samples" in system_prompt
    assert "business distribution" in system_prompt
    assert "untrusted data" in system_prompt
    document = json.loads(str(call["user_prompt"]))
    evidence = document["audit_evidence"]
    assert set(evidence) == {
        "dataset_summary",
        "issue_groups",
        "health_score",
        "class_distribution",
        "duplicate_summary",
        "knowledge_guidance",
        "representative_evidence",
    }
    assert evidence["knowledge_guidance"]["profile_id"] == "generic"
    assert evidence["knowledge_guidance"]["pack_schema_version"] == "1.0.0"
    assert "advisory" in system_prompt.lower()
    assert len(evidence["representative_evidence"]) <= 5
    assert all("issue_id" in item for item in evidence["representative_evidence"])
    assert "images" not in evidence
    assert "annotations" not in evidence
    assert "raw_line" not in str(evidence)


@pytest.mark.parametrize(
    "response",
    [
        "",
        "not json",
        '{"generated_by":"llm","risk_level":"medium","summary":""}',
        TimeoutError("request timed out"),
        RuntimeError("network unavailable"),
    ],
)
def test_invalid_or_failed_llm_automatically_falls_back(
    tmp_path: Path, response: str | Exception
) -> None:
    diagnosis = diagnose_report(
        _report(tmp_path),
        _enabled_config(),
        client=FakeClient(response),
    )

    assert diagnosis.generated_by == "deterministic"


def test_disabled_or_missing_key_never_calls_client(tmp_path: Path) -> None:
    report = _report(tmp_path)
    fake = FakeClient(AssertionError("client must not be called"))

    disabled = diagnose_report(report, LLMConfig(), client=fake)
    missing_key = diagnose_report(
        report,
        LLMConfig(enabled=True, model="fake-model"),
        client=fake,
    )

    assert disabled.generated_by == "deterministic"
    assert missing_key.generated_by == "deterministic"
    assert fake.calls == []


def test_unattempted_outcomes_are_distinct_and_never_call_client(
    tmp_path: Path,
) -> None:
    report = _report(tmp_path)
    fake = FakeClient(AssertionError("client must not be called"))

    disabled = diagnose_report_with_status(report, LLMConfig(), client=fake)
    missing_key = diagnose_report_with_status(
        report,
        LLMConfig(enabled=True, model="fake-model"),
        client=fake,
    )
    missing_model = diagnose_report_with_status(
        report,
        LLMConfig(enabled=True, api_key="unit-test-key"),
        client=fake,
    )

    assert disabled.failure_stage is LLMFailureStage.LLM_DISABLED
    assert missing_key.failure_stage is LLMFailureStage.CREDENTIALS_MISSING
    assert missing_model.failure_stage is LLMFailureStage.MODEL_MISSING
    assert all(
        outcome.diagnosis.generated_by == "deterministic"
        and outcome.live_api_verified is False
        for outcome in (disabled, missing_key, missing_model)
    )
    assert fake.calls == []


def test_errors_do_not_leak_key_and_unknown_issue_ids_fall_back(
    tmp_path: Path,
) -> None:
    report = _report(tmp_path)
    secret = "super-secret-test-key"
    leaking_error = FakeClient(RuntimeError(f"failed with {secret}"))
    failure = diagnose_report(report, _enabled_config(secret), client=leaking_error)
    unknown_reference = json.loads(_valid_llm_json())
    unknown_reference["priority_findings"] = [
        {
            "rank": 1,
            "title": "Invented",
            "rationale": "Unsupported reference.",
            "severity": "warning",
            "issue_ids": ["unknown-issue"],
        }
    ]
    invalid_evidence = diagnose_report(
        report,
        _enabled_config(secret),
        client=FakeClient(json.dumps(unknown_reference)),
    )

    assert failure.generated_by == "deterministic"
    assert invalid_evidence.generated_by == "deterministic"
    assert secret not in failure.model_dump_json()
    assert secret not in invalid_evidence.model_dump_json()


def test_payload_builder_exposes_only_aggregate_and_sampled_evidence(
    tmp_path: Path,
) -> None:
    report = _report(tmp_path)

    payload = build_agent_payload(report, max_representative_evidence=2)
    system_prompt, user_prompt = build_prompts(
        report, max_representative_evidence=2
    )

    assert len(payload["representative_evidence"]) == 2
    assert "Diagnosis JSON" in system_prompt
    assert json.loads(user_prompt)["audit_evidence"] == payload
    assert isinstance(FakeClient(_valid_llm_json()), DatasetDoctorClient)


def test_deepseek_adapter_sends_chat_json_request_to_fake_sdk() -> None:
    constructor_calls: list[dict[str, object]] = []
    request_calls: list[dict[str, object]] = []

    class FakeCompletions:
        def create(self, **kwargs):
            request_calls.append(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=_valid_llm_json())
                    )
                ]
            )

    def fake_factory(**kwargs):
        constructor_calls.append(kwargs)
        return SimpleNamespace(
            chat=SimpleNamespace(completions=FakeCompletions())
        )

    adapter = OpenAICompatibleDatasetDoctorClient(
        "unit-test-key",
        provider="deepseek",
        base_url="https://api.deepseek.com",
        max_retries=0,
        sdk_factory=fake_factory,
    )
    result = adapter.complete(
        system_prompt="Return Diagnosis JSON only.",
        user_prompt='{"audit_evidence":{}}',
        model="deepseek-flash",
        timeout_seconds=12,
    )

    assert result == _valid_llm_json()
    assert constructor_calls == [
        {
            "api_key": "unit-test-key",
            "timeout": 12,
            "max_retries": 0,
            "base_url": "https://api.deepseek.com",
        }
    ]
    assert len(request_calls) == 1
    request = request_calls[0]
    assert request["model"] == "deepseek-flash"
    assert request["messages"] == [
        {"role": "system", "content": "Return Diagnosis JSON only."},
        {"role": "user", "content": '{"audit_evidence":{}}'},
    ]
    assert request["response_format"] == {"type": "json_object"}
    assert request["stream"] is False
    assert request["max_tokens"] == 4_000
    assert request["extra_body"] == {"thinking": {"type": "disabled"}}


def test_deepseek_adapter_normalizes_fake_sdk_tool_call() -> None:
    requests: list[dict[str, object]] = []

    class FakeCompletions:
        def create(self, **kwargs):
            requests.append(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    id="call-1",
                                    function=SimpleNamespace(
                                        name="get_score_component",
                                        arguments='{"component":"image"}',
                                    ),
                                )
                            ],
                        )
                    )
                ]
            )

    adapter = OpenAICompatibleDatasetDoctorClient(
        "unit-test-key",
        provider="deepseek",
        base_url="https://api.deepseek.com",
        max_retries=0,
        sdk_factory=lambda **kwargs: SimpleNamespace(
            chat=SimpleNamespace(completions=FakeCompletions())
        ),
    )
    turn = adapter.complete_tool_turn(
        messages=[{"role": "user", "content": "query"}],
        tools=[{"type": "function", "function": {"name": "tool"}}],
        model="deepseek-flash",
        timeout_seconds=12,
    )

    assert turn.tool_calls[0].name == "get_score_component"
    assert turn.tool_calls[0].arguments_json == '{"component":"image"}'
    assert requests[0]["tool_choice"] == "auto"
    assert requests[0]["response_format"] == {"type": "json_object"}


def test_tool_query_loop_executes_bounded_read_only_call_then_accepts_json(
    tmp_path: Path,
) -> None:
    report = _report(tmp_path)
    payload = json.loads(_valid_llm_json())
    payload["evidence_claims"] = [
        {
            "claim_type": "score_penalty",
            "metric_name": "image",
            "claimed_value": report.health_score.penalties["image"],
            "source_tool": "get_score_component",
            "related_issue_ids": [],
            "classification": "fact",
        }
    ]
    fake = FakeToolClient(
        [
            EvidenceToolTurn(
                tool_calls=[
                    EvidenceToolCall(
                        call_id="call-1",
                        name="get_score_component",
                        arguments_json='{"component":"image"}',
                    )
                ]
            ),
            EvidenceToolTurn(content=json.dumps(payload)),
        ]
    )

    outcome = diagnose_report_with_status(
        report,
        _enabled_config(),
        client=fake,
    )

    assert outcome.diagnosis.generated_by == "llm"
    assert outcome.failure_stage is None
    assert outcome.execution_mode == "evidence_query"
    assert len(fake.calls) == 2
    second_messages = fake.calls[1]["messages"]
    assert any(message["role"] == "tool" for message in second_messages)
    tool_message = next(
        message for message in second_messages if message["role"] == "tool"
    )
    assert json.loads(tool_message["content"])["component"] == "image"
    assert "raw_line" not in tool_message["content"]


@pytest.mark.parametrize(
    ("call", "expected_stage"),
    [
        (
            EvidenceToolCall(
                call_id="unknown",
                name="run_command",
                arguments_json="{}",
            ),
            LLMFailureStage.UNKNOWN_TOOL,
        ),
        (
            EvidenceToolCall(
                call_id="bad-args",
                name="get_score_component",
                arguments_json='{"component":"invalid"}',
            ),
            LLMFailureStage.TOOL_ARGUMENT_ERROR,
        ),
    ],
)
def test_unknown_tool_or_invalid_arguments_use_sanitized_fallback(
    tmp_path: Path,
    call: EvidenceToolCall,
    expected_stage: LLMFailureStage,
) -> None:
    outcome = diagnose_report_with_status(
        _report(tmp_path),
        _enabled_config(),
        client=FakeToolClient([EvidenceToolTurn(tool_calls=[call])]),
    )

    assert outcome.failure_stage is expected_stage
    assert outcome.diagnosis.generated_by == "deterministic"


def test_tool_round_limit_uses_fallback(tmp_path: Path) -> None:
    call = EvidenceToolCall(
        call_id="call-1",
        name="get_dataset_summary",
        arguments_json="{}",
    )
    second_call = call.model_copy(update={"call_id": "call-2"})
    config = _enabled_config().model_copy(update={"max_tool_rounds": 1})

    outcome = diagnose_report_with_status(
        _report(tmp_path),
        config,
        client=FakeToolClient(
            [
                EvidenceToolTurn(tool_calls=[call]),
                EvidenceToolTurn(tool_calls=[second_call]),
            ]
        ),
    )

    assert outcome.failure_stage is LLMFailureStage.TOOL_ROUND_LIMIT
    assert outcome.diagnosis.generated_by == "deterministic"


def test_malformed_tool_protocol_uses_fallback(tmp_path: Path) -> None:
    fake = FakeToolClient(
        [
            {
                "content": None,
                "tool_calls": [{"unexpected": "provider-shape"}],
            }
        ]
    )

    outcome = diagnose_report_with_status(
        _report(tmp_path),
        _enabled_config(),
        client=fake,
    )

    assert outcome.failure_stage is LLMFailureStage.TOOL_PROTOCOL_ERROR
    assert outcome.diagnosis.generated_by == "deterministic"


def test_total_evidence_and_per_result_limits_use_fallback(tmp_path: Path) -> None:
    call = EvidenceToolCall(
        call_id="large",
        name="get_representative_issues",
        arguments_json='{"limit":10}',
    )
    total_limited = _enabled_config().model_copy(
        update={"max_total_evidence_bytes": 1024}
    )
    result_limited = _enabled_config().model_copy(
        update={"max_tool_result_bytes": 1024}
    )

    total_outcome = diagnose_report_with_status(
        _report(tmp_path),
        total_limited,
        client=FakeToolClient([EvidenceToolTurn(tool_calls=[call])]),
    )
    result_outcome = diagnose_report_with_status(
        _report(tmp_path),
        result_limited,
        client=FakeToolClient([EvidenceToolTurn(tool_calls=[call])]),
    )

    assert total_outcome.failure_stage is LLMFailureStage.EVIDENCE_LIMIT_EXCEEDED
    assert result_outcome.failure_stage is LLMFailureStage.EVIDENCE_LIMIT_EXCEEDED


def test_fact_mismatch_and_prohibited_claims_fall_back(tmp_path: Path) -> None:
    report = _report(tmp_path)
    incorrect = json.loads(_valid_llm_json())
    incorrect["evidence_claims"] = [
        {
            "claim_type": "health_score",
            "metric_name": "overall",
            "claimed_value": 99.9,
            "source_tool": "get_score_component",
            "classification": "fact",
        }
    ]
    incorrect_count = json.loads(_valid_llm_json())
    incorrect_count["evidence_claims"] = [
        {
            "claim_type": "dataset_count",
            "metric_name": "image_count",
            "claimed_value": 999,
            "source_tool": "get_dataset_summary",
            "classification": "fact",
        }
    ]
    promise = json.loads(_valid_llm_json())
    promise["summary"] = "We guarantee this repair will improve mAP."
    modified = json.loads(_valid_llm_json())
    modified["summary"] = "VisionDoctor already modified the labels."

    mismatch = diagnose_report_with_status(
        report,
        _enabled_config(),
        client=FakeClient(json.dumps(incorrect)),
    )
    count_mismatch = diagnose_report_with_status(
        report,
        _enabled_config(),
        client=FakeClient(json.dumps(incorrect_count)),
    )
    prohibited = diagnose_report_with_status(
        report,
        _enabled_config(),
        client=FakeClient(json.dumps(promise)),
    )
    modification_claim = diagnose_report_with_status(
        report,
        _enabled_config(),
        client=FakeClient(json.dumps(modified)),
    )

    assert mismatch.failure_stage is LLMFailureStage.FACT_CLAIM_MISMATCH
    assert count_mismatch.failure_stage is LLMFailureStage.FACT_CLAIM_MISMATCH
    assert prohibited.failure_stage is (
        LLMFailureStage.PROHIBITED_PERFORMANCE_PROMISE
    )
    assert modification_claim.failure_stage is LLMFailureStage.DATA_MODIFICATION_CLAIM
    assert mismatch.diagnosis.generated_by == "deterministic"
    assert prohibited.diagnosis.generated_by == "deterministic"
    assert modification_claim.diagnosis.generated_by == "deterministic"


def test_adapter_empty_content_maps_to_empty_response_stage(tmp_path: Path) -> None:
    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="  "))]
            )

    def fake_factory(**kwargs):
        return SimpleNamespace(
            chat=SimpleNamespace(completions=FakeCompletions())
        )

    adapter = OpenAICompatibleDatasetDoctorClient(
        "unit-test-key",
        provider="deepseek",
        base_url="https://api.deepseek.com",
        max_retries=0,
        sdk_factory=fake_factory,
    )
    outcome = diagnose_report_with_status(
        _report(tmp_path),
        _enabled_config(),
        client=adapter,
    )

    assert outcome.failure_stage is LLMFailureStage.EMPTY_RESPONSE
    assert outcome.live_api_verified is False


def test_missing_key_does_not_construct_sdk_adapter(
    tmp_path: Path, monkeypatch
) -> None:
    def unexpected_constructor(*args, **kwargs):
        raise AssertionError("SDK adapter must not be constructed")

    monkeypatch.setattr(
        client_module,
        "OpenAICompatibleDatasetDoctorClient",
        unexpected_constructor,
    )
    diagnosis = diagnose_report(
        _report(tmp_path),
        LLMConfig(
            enabled=True,
            provider="deepseek",
            model="deepseek-flash",
        ),
    )

    assert diagnosis.generated_by == "deterministic"


def test_provider_exception_does_not_log_key(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "never-log-this-unit-test-key"

    diagnosis = diagnose_report(
        _report(tmp_path),
        _enabled_config(secret),
        client=FakeClient(RuntimeError(f"provider rejected {secret}")),
    )

    assert diagnosis.generated_by == "deterministic"
    assert secret not in caplog.text


@pytest.mark.parametrize(
    ("error", "expected_stage"),
    [
        (TimeoutError("sensitive timeout detail"), LLMFailureStage.REQUEST_TIMEOUT),
        (
            type("APITimeoutError", (Exception,), {})("sensitive timeout detail"),
            LLMFailureStage.REQUEST_TIMEOUT,
        ),
        (
            type("AuthenticationError", (Exception,), {})("sensitive auth detail"),
            LLMFailureStage.AUTHENTICATION_ERROR,
        ),
        (
            type("RateLimitError", (Exception,), {})("sensitive balance detail"),
            LLMFailureStage.RATE_LIMIT_OR_BALANCE_ERROR,
        ),
        (
            type("APIConnectionError", (Exception,), {})("sensitive network detail"),
            LLMFailureStage.CONNECTION_ERROR,
        ),
        (
            type("APIStatusError", (Exception,), {})("sensitive response detail"),
            LLMFailureStage.PROVIDER_API_ERROR,
        ),
        (ModuleNotFoundError("sensitive sdk detail"), LLMFailureStage.SDK_UNAVAILABLE),
        (RuntimeError("sensitive unknown detail"), LLMFailureStage.UNKNOWN_ERROR),
    ],
)
def test_provider_errors_are_classified_by_type_without_detail_leakage(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    expected_stage: LLMFailureStage,
) -> None:
    secret = "classification-test-secret"

    outcome = diagnose_report_with_status(
        _report(tmp_path),
        _enabled_config(secret),
        client=FakeClient(error),
    )

    assert outcome.failure_stage is expected_stage
    assert outcome.diagnosis.generated_by == "deterministic"
    assert outcome.live_api_verified is False
    assert secret not in str(outcome)
    assert str(error) not in str(outcome)
    assert secret not in caplog.text
    assert str(error) not in caplog.text


@pytest.mark.parametrize(
    ("response", "expected_stage"),
    [
        ("", LLMFailureStage.EMPTY_RESPONSE),
        ("   ", LLMFailureStage.EMPTY_RESPONSE),
        ("not json", LLMFailureStage.INVALID_JSON),
        (
            '{"generated_by":"llm","risk_level":"medium","summary":""}',
            LLMFailureStage.DIAGNOSIS_SCHEMA_ERROR,
        ),
    ],
)
def test_response_validation_failure_stages_are_distinct(
    tmp_path: Path,
    response: str,
    expected_stage: LLMFailureStage,
) -> None:
    outcome = diagnose_report_with_status(
        _report(tmp_path),
        _enabled_config(),
        client=FakeClient(response),
    )

    assert outcome.failure_stage is expected_stage
    assert outcome.diagnosis.generated_by == "deterministic"
    assert outcome.live_api_verified is False


def test_invalid_raw_response_is_not_retained_or_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    raw_response = "unique-sensitive-raw-provider-response"

    outcome = diagnose_report_with_status(
        _report(tmp_path),
        _enabled_config(),
        client=FakeClient(raw_response),
    )

    assert outcome.failure_stage is LLMFailureStage.INVALID_JSON
    assert raw_response not in str(outcome)
    assert raw_response not in caplog.text


def test_generated_by_mismatch_has_distinct_stage(tmp_path: Path) -> None:
    payload = json.loads(_valid_llm_json())
    payload["generated_by"] = "deterministic"

    outcome = diagnose_report_with_status(
        _report(tmp_path),
        _enabled_config(),
        client=FakeClient(json.dumps(payload)),
    )

    assert outcome.failure_stage is LLMFailureStage.GENERATED_BY_MISMATCH
    assert outcome.diagnosis.generated_by == "deterministic"


def test_unknown_issue_reference_has_distinct_stage(tmp_path: Path) -> None:
    payload = json.loads(_valid_llm_json())
    payload["recommended_actions"] = [
        {
            "action_id": "unsafe-reference",
            "priority": 1,
            "title": "Unsupported action",
            "description": "References evidence that was not supplied.",
            "related_issue_ids": ["unknown-issue"],
            "estimated_effort": "low",
        }
    ]

    outcome = diagnose_report_with_status(
        _report(tmp_path),
        _enabled_config(),
        client=FakeClient(json.dumps(payload)),
    )

    assert outcome.failure_stage is LLMFailureStage.UNKNOWN_ISSUE_REFERENCE
    assert outcome.diagnosis.generated_by == "deterministic"


def test_compatibility_wrapper_still_returns_diagnosis(tmp_path: Path) -> None:
    diagnosis = diagnose_report(
        _report(tmp_path),
        _enabled_config(),
        client=FakeClient(_valid_llm_json()),
    )

    assert diagnosis.generated_by == "llm"
    assert not isinstance(diagnosis, DiagnosisOutcome)
