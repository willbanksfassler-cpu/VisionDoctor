"""Tests for non-mutating, explicitly hypothetical repair-score previews."""

from __future__ import annotations

from pathlib import Path

from scripts.generate_demo_dataset import generate_demo_zip
from vision_doctor.models import RepairScenario
from vision_doctor.pipeline import run_pipeline
from vision_doctor.repair_simulation import simulate_repairs


def _report(tmp_path: Path):
    return run_pipeline(
        generate_demo_zip(tmp_path / "demo.zip"),
        temp_root=tmp_path,
    )


def test_selected_issue_preview_is_deterministic_and_does_not_mutate_input(
    tmp_path: Path,
) -> None:
    report = _report(tmp_path)
    selected = next(issue for issue in report.issues if issue.code == "LABEL_MISSING")
    scenario = RepairScenario(
        scenario_id="selected-issue",
        title="Resolve selected finding",
        selection_kind="issue_ids",
        issue_ids=[selected.issue_id],
        suggested_action="Review the selected evidence.",
        estimated_effort="low",
        assumptions=["The selected finding no longer applies."],
    )
    sentinel = tmp_path / "source-sentinel.txt"
    sentinel.write_text("unchanged", encoding="utf-8")
    before = report.model_dump_json()

    first = simulate_repairs(report, [scenario])
    second = simulate_repairs(report, [scenario])

    assert first == second
    assert report.model_dump_json() == before
    assert sentinel.read_text(encoding="utf-8") == "unchanged"
    impact = first.impacts[0]
    assert impact.affected_issue_ids == [selected.issue_id]
    assert impact.affected_issue_count == 1
    assert impact.source_data_modified is False
    assert 0.0 <= impact.original_score <= 100.0
    assert 0.0 <= impact.simulated_score <= 100.0
    assert impact.score_delta >= 0.0


def test_supported_scenario_kinds_record_assumptions_and_dependencies(
    tmp_path: Path,
) -> None:
    report = _report(tmp_path)
    group = report.duplicate_groups[0]
    scenarios = [
        RepairScenario(
            scenario_id="by-code",
            title="Resolve blurry images",
            selection_kind="issue_code",
            issue_code="IMAGE_BLURRY",
            suggested_action="Review image focus.",
            estimated_effort="medium",
            assumptions=["Every blurry-image finding is resolved."],
        ),
        RepairScenario(
            scenario_id="duplicate",
            title="Resolve duplicate group",
            selection_kind="duplicate_group",
            duplicate_group_id=group.group_id,
            suggested_action="Confirm provenance before deduplication.",
            estimated_effort="low",
            assumptions=["The duplicate relationship is removed."],
        ),
        RepairScenario(
            scenario_id="unreadable",
            title="Exclude unreadable images",
            selection_kind="exclude_unreadable",
            suggested_action="Confirm unusable images before exclusion.",
            estimated_effort="low",
            assumptions=["Unreadable images are excluded from the audit."],
        ),
        RepairScenario(
            scenario_id="leakage",
            title="Resolve split leakage",
            selection_kind="fix_split_leakage",
            suggested_action="Review split provenance.",
            estimated_effort="medium",
            assumptions=["All leakage groups are resolved."],
        ),
    ]

    simulation = simulate_repairs(report, scenarios)

    assert [impact.scenario.selection_kind for impact in simulation.impacts] == [
        "issue_code",
        "duplicate_group",
        "exclude_unreadable",
        "fix_split_leakage",
    ]
    assert simulation.impacts[1].affected_duplicate_group_ids == [group.group_id]
    assert simulation.impacts[2].affected_issue_count >= 1
    assert simulation.impacts[3].affected_duplicate_group_ids
    assert all(impact.assumptions for impact in simulation.impacts)
    assert all(
        any("mAP" in caveat for caveat in impact.caveats)
        for impact in simulation.impacts
    )


def test_default_preview_is_limited_to_ranked_top_five(tmp_path: Path) -> None:
    report = _report(tmp_path)

    simulation = simulate_repairs(report)

    assert 1 <= len(simulation.impacts) <= 5
    assert simulation.profile_name == "legacy-v1"
    assert simulation.impacts == sorted(
        simulation.impacts,
        key=lambda item: (
            -item.score_delta,
            -item.affected_issue_count,
            item.scenario.scenario_id,
        ),
    )
