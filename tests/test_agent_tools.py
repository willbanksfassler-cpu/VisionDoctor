"""Tests for bounded, read-only Dataset Doctor evidence queries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.generate_demo_dataset import generate_demo_zip
from vision_doctor.agent.evidence_tools import (
    TOOL_NAMES,
    EvidenceLimitError,
    EvidenceQueryService,
    EvidenceToolArgumentsError,
    UnknownEvidenceToolError,
)
from vision_doctor.config import LLMConfig
from vision_doctor.pipeline import run_pipeline


def _report(tmp_path: Path):
    return run_pipeline(
        generate_demo_zip(tmp_path / "demo.zip"),
        temp_root=tmp_path,
    )


def test_all_read_only_tools_return_stable_bounded_json(tmp_path: Path) -> None:
    report = _report(tmp_path)
    before = report.model_dump_json()
    service = EvidenceQueryService(report, max_items=2)
    calls = {
        "get_dataset_summary": {},
        "get_issue_group": {"code": "IMAGE_BLURRY"},
        "get_representative_issues": {"limit": 20},
        "get_class_distribution": {"limit": 20},
        "get_score_component": {"component": "image"},
        "get_duplicate_summary": {"kind": "all", "limit": 20},
        "get_split_leakage_summary": {"kind": "all", "limit": 20},
        "get_repair_simulations": {"limit": 5},
    }

    assert tuple(calls) == TOOL_NAMES
    for name, arguments in calls.items():
        first = service.execute(name, arguments)
        second = service.execute(name, arguments)
        assert first == second
        payload = json.loads(first)
        assert payload["source_tool"] == name
        assert "raw_line" not in first
        assert "image_bytes" not in first
        assert "annotations" not in payload
    assert len(json.loads(service.execute("get_representative_issues", {"limit": 20}))["items"]) <= 2
    assert len(json.loads(service.execute("get_class_distribution", {"limit": 20}))["classes"]) <= 2
    assert report.model_dump_json() == before


def test_tool_definitions_are_fixed_and_reject_path_url_command_or_extra_fields(
    tmp_path: Path,
) -> None:
    service = EvidenceQueryService(_report(tmp_path))
    definitions = service.tool_definitions()

    assert [item["function"]["name"] for item in definitions] == list(TOOL_NAMES)
    assert all(item["function"]["strict"] is True for item in definitions)
    assert all(
        item["function"]["parameters"].get("additionalProperties") is False
        for item in definitions
    )
    with pytest.raises(EvidenceToolArgumentsError):
        service.execute(
            "get_dataset_summary",
            {"path": "../../secret", "url": "https://example.invalid"},
        )
    with pytest.raises(EvidenceToolArgumentsError):
        service.execute("get_issue_group", {"code": "$(whoami)"})
    with pytest.raises(EvidenceToolArgumentsError):
        service.execute_json_arguments("get_dataset_summary", "[]")
    with pytest.raises(UnknownEvidenceToolError):
        service.execute("run_command", {"command": "whoami"})


def test_tool_response_byte_limit_is_enforced(tmp_path: Path) -> None:
    service = EvidenceQueryService(_report(tmp_path), max_result_bytes=1)

    with pytest.raises(EvidenceLimitError):
        service.execute("get_dataset_summary", {})


def test_specific_tool_facts_match_audit_report(tmp_path: Path) -> None:
    report = _report(tmp_path)
    service = EvidenceQueryService(report)

    summary = json.loads(service.execute("get_dataset_summary", {}))
    score = json.loads(
        service.execute("get_score_component", {"component": "duplicates"})
    )
    duplicate = json.loads(
        service.execute("get_duplicate_summary", {"kind": "all"})
    )
    leakage = json.loads(
        service.execute("get_split_leakage_summary", {"kind": "all"})
    )

    assert summary["summary"]["image_count"] == report.manifest.summary.image_count
    assert score["penalty"] == report.health_score.penalties["duplicates"]
    assert duplicate["matched_group_count"] == len(report.duplicate_groups)
    assert leakage["matched_group_count"] == 1


def test_tool_round_and_evidence_limits_are_bounded_by_configuration() -> None:
    config = LLMConfig()

    assert config.max_tool_rounds == 3
    assert config.max_tool_calls_per_round == 3
    assert config.max_total_evidence_bytes == 24_000
    with pytest.raises(ValidationError):
        LLMConfig(max_tool_rounds=4)
