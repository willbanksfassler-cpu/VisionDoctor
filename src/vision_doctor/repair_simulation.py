"""Pure in-memory, deterministic repair-impact previews."""

from __future__ import annotations

import hashlib
import json
from collections import Counter

from vision_doctor.checkers.distribution import calculate_distribution
from vision_doctor.models import (
    AuditReport,
    DatasetManifest,
    DuplicateGroup,
    Issue,
    RepairImpact,
    RepairScenario,
    RepairSimulationReport,
)
from vision_doctor.scoring import (
    calculate_health_score,
    score_profile_from_health_score,
)

_LEAKAGE_CODES = {"SPLIT_LEAKAGE_EXACT", "SPLIT_LEAKAGE_NEAR"}
_HUMAN_REVIEW_CODES = {
    "BBOX_AREA_OUTLIER",
    "BBOX_ASPECT_RATIO_OUTLIER",
    "SPLIT_LEAKAGE_NEAR",
}


def _stable_scenario_id(kind: str, value: str) -> str:
    payload = json.dumps([kind, value], separators=(",", ":"))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"repair-{digest}"


def _effort(count: int) -> str:
    if count <= 2:
        return "low"
    if count <= 10:
        return "medium"
    return "high"


def _group_id_from_issue(issue: Issue) -> str | None:
    value = issue.evidence.get("duplicate_group_id")
    return value if isinstance(value, str) and value else None


def default_repair_scenarios(report: AuditReport) -> list[RepairScenario]:
    """Build deterministic candidates from observed facts, not invented repairs."""

    scenarios: list[RepairScenario] = []
    counts = Counter(issue.code for issue in report.issues)
    for code, count in sorted(counts.items()):
        scenarios.append(
            RepairScenario(
                scenario_id=_stable_scenario_id("issue_code", code),
                title=f"假设所有 {code} 问题都已解决",
                selection_kind="issue_code",
                issue_code=code,
                suggested_action=(
                    "逐项复核引用证据，确认底层数据问题后再修改源数据。"
                ),
                estimated_effort=_effort(count),
                assumptions=[
                    f"假设检测到的 {count} 个 {code} 问题均不再存在。"
                ],
                requires_human_confirmation=code in _HUMAN_REVIEW_CODES,
            )
        )
    for group in sorted(report.duplicate_groups, key=lambda item: item.group_id):
        scenarios.append(
            RepairScenario(
                scenario_id=_stable_scenario_id(
                    "duplicate_group",
                    group.group_id,
                ),
                title=f"假设重复组 {group.group_id} 已解决",
                selection_kind="duplicate_group",
                duplicate_group_id=group.group_id,
                suggested_action=(
                    "删除或重新分配重复图片前，先确认来源并保留适当的源图片。"
                ),
                estimated_effort="low" if len(group.image_ids) <= 3 else "medium",
                assumptions=[
                    "假设经过复核后，所选重复关系已不再存在。"
                ],
                requires_human_confirmation=True,
            )
        )
    if any(issue.code == "IMAGE_UNREADABLE" for issue in report.issues):
        scenarios.append(
            RepairScenario(
                scenario_id=_stable_scenario_id(
                    "exclude_unreadable",
                    "all",
                ),
                title="假设不可读图片已从本次体检中排除",
                selection_kind="exclude_unreadable",
                suggested_action=(
                    "从数据集版本中排除图片前，确认图片确实不可用，并检查配对标签。"
                ),
                estimated_effort="low",
                assumptions=[
                    "假设不可读图片及其相关体检证据已被排除。"
                ],
                requires_human_confirmation=True,
            )
        )
    if any(issue.code in _LEAKAGE_CODES for issue in report.issues):
        scenarios.append(
            RepairScenario(
                scenario_id=_stable_scenario_id("fix_split_leakage", "all"),
                title="假设所有跨 split 泄漏组都已解决",
                selection_kind="fix_split_leakage",
                suggested_action=(
                    "复核数据来源和划分策略，确保每个确认样本只保留在预期 split 中。"
                ),
                estimated_effort="medium",
                assumptions=[
                    "假设所有引用的跨 split 重复组均已在复核后解决。"
                ],
                requires_human_confirmation=True,
            )
        )
    return scenarios


def _without_excluded_images(
    manifest: DatasetManifest,
    excluded_image_ids: set[str],
) -> DatasetManifest:
    images = [
        image for image in manifest.images if image.image_id not in excluded_image_ids
    ]
    annotations = [
        annotation
        for annotation in manifest.annotations
        if annotation.image_id not in excluded_image_ids
    ]
    unreadable = [
        path
        for path in manifest.unreadable_image_paths
        if path not in excluded_image_ids
    ]
    summary = manifest.summary.model_copy(
        update={
            "image_count": max(
                manifest.summary.image_count - len(excluded_image_ids),
                0,
            ),
            "annotation_count": len(annotations),
        }
    )
    return manifest.model_copy(
        update={
            "images": images,
            "annotations": annotations,
            "unreadable_image_paths": unreadable,
            "summary": summary,
        }
    )


def _without_excluded_group_members(
    groups: list[DuplicateGroup],
    excluded_image_ids: set[str],
) -> list[DuplicateGroup]:
    remaining_groups: list[DuplicateGroup] = []
    for group in groups:
        image_ids = [
            image_id
            for image_id in group.image_ids
            if image_id not in excluded_image_ids
        ]
        if len(image_ids) < 2:
            continue
        pairs = {
            pair: distance
            for pair, distance in group.pair_distances.items()
            if all(member not in excluded_image_ids for member in pair.split("|"))
        }
        remaining_groups.append(
            group.model_copy(
                update={
                    "image_ids": image_ids,
                    "representative_image_id": image_ids[0],
                    "pair_distances": pairs,
                }
            )
        )
    return remaining_groups


def _simulate_one(report: AuditReport, scenario: RepairScenario) -> RepairImpact:
    remove_issue_ids: set[str] = set()
    remove_group_ids: set[str] = set()
    excluded_image_ids: set[str] = set()

    if scenario.selection_kind == "issue_ids":
        remove_issue_ids.update(scenario.issue_ids)
    elif scenario.selection_kind == "issue_code":
        remove_issue_ids.update(
            issue.issue_id
            for issue in report.issues
            if issue.code == scenario.issue_code
        )
    elif scenario.selection_kind == "duplicate_group":
        if scenario.duplicate_group_id is not None:
            remove_group_ids.add(scenario.duplicate_group_id)
    elif scenario.selection_kind == "exclude_unreadable":
        unreadable = [
            issue for issue in report.issues if issue.code == "IMAGE_UNREADABLE"
        ]
        excluded_image_ids.update(
            issue.image_id or issue.relative_path or "" for issue in unreadable
        )
        excluded_image_ids.discard("")
        remove_issue_ids.update(issue.issue_id for issue in unreadable)
    elif scenario.selection_kind == "fix_split_leakage":
        leakage = [
            issue for issue in report.issues if issue.code in _LEAKAGE_CODES
        ]
        remove_issue_ids.update(issue.issue_id for issue in leakage)
        remove_group_ids.update(
            group_id
            for issue in leakage
            if (group_id := _group_id_from_issue(issue)) is not None
        )

    selected_issues = [
        issue for issue in report.issues if issue.issue_id in remove_issue_ids
    ]
    remove_group_ids.update(
        group_id
        for issue in selected_issues
        if issue.code in _LEAKAGE_CODES
        and (group_id := _group_id_from_issue(issue)) is not None
    )
    for issue in report.issues:
        if _group_id_from_issue(issue) in remove_group_ids:
            remove_issue_ids.add(issue.issue_id)

    manifest = (
        _without_excluded_images(report.manifest, excluded_image_ids)
        if excluded_image_ids
        else report.manifest
    )
    issues = [
        issue
        for issue in report.issues
        if issue.issue_id not in remove_issue_ids
        and issue.image_id not in excluded_image_ids
    ]
    groups = [
        group
        for group in report.duplicate_groups
        if group.group_id not in remove_group_ids
    ]
    if excluded_image_ids:
        groups = _without_excluded_group_members(groups, excluded_image_ids)
    distribution = (
        calculate_distribution(manifest)
        if excluded_image_ids
        else report.distribution
    )
    profile = score_profile_from_health_score(report.health_score)
    simulated = calculate_health_score(
        manifest,
        issues,
        groups,
        distribution,
        profile=profile,
    )
    caveats = [
        "这只是健康分的假设计算，没有修改任何图片或标签。",
        "分数变化不能预测 mAP、训练质量或业务效果。",
    ]
    if scenario.requires_human_confirmation:
        caveats.append(
            "该假设修复存在依赖或歧义，需要人工确认。"
        )
    return RepairImpact(
        scenario=scenario,
        original_score=report.health_score.overall,
        simulated_score=simulated.overall,
        score_delta=round(simulated.overall - report.health_score.overall, 2),
        affected_issue_ids=sorted(remove_issue_ids),
        affected_issue_count=len(remove_issue_ids),
        affected_duplicate_group_ids=sorted(remove_group_ids),
        assumptions=list(scenario.assumptions),
        caveats=caveats,
        source_data_modified=False,
    )


def simulate_repairs(
    report: AuditReport,
    scenarios: list[RepairScenario] | None = None,
    *,
    max_scenarios: int = 5,
) -> RepairSimulationReport:
    """Return deterministic score previews without reading or writing source files."""

    if not 1 <= max_scenarios <= 5:
        raise ValueError("max_scenarios must be between 1 and 5")
    candidates = scenarios if scenarios is not None else default_repair_scenarios(report)
    impacts = [_simulate_one(report, scenario) for scenario in candidates]
    if scenarios is None:
        impacts.sort(
            key=lambda item: (
                -item.score_delta,
                -item.affected_issue_count,
                item.scenario.scenario_id,
            )
        )
    return RepairSimulationReport(
        methodology_version="1.0.0",
        profile_name=report.health_score.profile_name,
        impacts=impacts[:max_scenarios],
    )


__all__ = ["default_repair_scenarios", "simulate_repairs"]
