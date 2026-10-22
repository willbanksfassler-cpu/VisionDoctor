"""Tests for the deterministic Dataset Doctor fallback."""

from __future__ import annotations

from pathlib import Path

from scripts.generate_demo_dataset import generate_demo_zip
from vision_doctor.config import Settings
from vision_doctor.pipeline import run_pipeline

_SEVERITY_RANK = {"info": 0, "warning": 1, "error": 2, "critical": 3}


def test_no_key_pipeline_returns_complete_deterministic_diagnosis(
    tmp_path: Path,
) -> None:
    archive = generate_demo_zip(tmp_path / "demo.zip")
    settings = Settings(_env_file=None)

    report = run_pipeline(
        archive,
        settings=settings,
        temp_root=tmp_path,
        run_doctor=True,
    )

    diagnosis = report.diagnosis
    assert diagnosis is not None
    assert diagnosis.generated_by == "deterministic"
    assert diagnosis.risk_level in {"low", "medium", "high", "critical"}
    assert str(report.health_score.overall) in diagnosis.summary
    assert diagnosis.priority_findings
    assert diagnosis.recommended_actions
    assert diagnosis.evidence_claims
    assert len(diagnosis.caveats) >= 4
    assert any("mAP" in caveat for caveat in diagnosis.caveats)
    assert any("合法负样本" in caveat for caveat in diagnosis.caveats)
    assert any("真实业务分布" in caveat for caveat in diagnosis.caveats)
    assert report.knowledge_guidance is not None
    assert report.knowledge_guidance.profile_id.value == "generic"
    assert any("当前场景知识包：generic" in item for item in diagnosis.caveats)
    assert any("知识包 1.0.0；仅供参考" in item.description for item in diagnosis.recommended_actions)

    ordering = [
        (
            _SEVERITY_RANK[finding.severity.value],
            finding.affected_count,
            finding.score_penalty,
        )
        for finding in diagnosis.priority_findings
    ]
    assert ordering == sorted(ordering, reverse=True)
    assert report.model_validate_json(report.model_dump_json()).diagnosis == diagnosis
    assert report.diagnosis_mode == "deterministic_fallback"
    assert report.diagnosis_failure_stage == "llm_disabled"


def test_fallback_is_stable_for_the_same_audit(tmp_path: Path) -> None:
    archive = generate_demo_zip(tmp_path / "demo.zip")
    settings = Settings(_env_file=None)

    first = run_pipeline(
        archive, settings=settings, temp_root=tmp_path, run_doctor=True
    ).diagnosis
    second = run_pipeline(
        archive, settings=settings, temp_root=tmp_path, run_doctor=True
    ).diagnosis

    assert first == second
