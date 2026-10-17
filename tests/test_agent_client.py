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
        "representative_evidence",
    }
    assert len(evidence["representative_evidence"]) <= 5
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
    assert request["max_tokens"] == 1_500
    assert request["extra_body"] == {"thinking": {"type": "disabled"}}


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
