"""Bounded, read-only evidence queries over an immutable AuditReport."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Mapping
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from vision_doctor.models import AuditReport, Issue, Severity

TOOL_NAMES = (
    "get_dataset_summary",
    "get_issue_group",
    "get_representative_issues",
    "get_class_distribution",
    "get_score_component",
    "get_duplicate_summary",
    "get_split_leakage_summary",
    "get_repair_simulations",
)

_SEVERITY_RANK = {
    Severity.INFO: 0,
    Severity.WARNING: 1,
    Severity.ERROR: 2,
    Severity.CRITICAL: 3,
}


class EvidenceToolError(Exception):
    """Base marker whose message is never exposed to users or logs."""


class UnknownEvidenceToolError(EvidenceToolError):
    """The model requested a tool outside the fixed allowlist."""


class EvidenceToolArgumentsError(EvidenceToolError):
    """Tool JSON or Pydantic arguments failed validation."""


class EvidenceLimitError(EvidenceToolError):
    """One tool response exceeded its configured byte ceiling."""


class QueryArguments(BaseModel):
    """Strict base that rejects arbitrary path, URL, command, and code fields."""

    model_config = ConfigDict(extra="forbid")


class EmptyArguments(QueryArguments):
    """No-argument query."""


class IssueGroupArguments(QueryArguments):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")


class RepresentativeIssuesArguments(QueryArguments):
    code: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]{1,63}$",
    )
    severity: Severity | None = None
    limit: int = Field(default=5, ge=1, le=20)


class ClassDistributionArguments(QueryArguments):
    class_ids: list[int] | None = Field(default=None, max_length=20)
    limit: int = Field(default=10, ge=1, le=20)

    @field_validator("class_ids")
    @classmethod
    def validate_class_ids(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return value
        if any(class_id < 0 for class_id in value):
            raise ValueError("class IDs must be non-negative")
        if len(set(value)) != len(value):
            raise ValueError("class IDs must be unique")
        return value


class ScoreComponentArguments(QueryArguments):
    component: Literal[
        "structural",
        "bbox",
        "image",
        "duplicates",
        "distribution",
    ]


class DuplicateSummaryArguments(QueryArguments):
    kind: Literal["all", "exact", "near"] = "all"
    limit: int = Field(default=5, ge=1, le=20)


class SplitLeakageArguments(QueryArguments):
    kind: Literal["all", "exact", "near"] = "all"
    limit: int = Field(default=5, ge=1, le=20)


class RepairSimulationsArguments(QueryArguments):
    limit: int = Field(default=5, ge=1, le=5)


def stable_json(value: object) -> str:
    """Serialize a tool response deterministically without NaN values."""

    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


class EvidenceQueryService:
    """Execute only predefined aggregate queries against one AuditReport."""

    def __init__(
        self,
        report: AuditReport,
        *,
        max_items: int = 10,
        max_result_bytes: int = 8_000,
    ) -> None:
        self._report = report
        self._max_items = max_items
        self._max_result_bytes = max_result_bytes
        self._registry: dict[
            str,
            tuple[type[QueryArguments], Callable[[QueryArguments], dict[str, Any]]],
        ] = {
            "get_dataset_summary": (EmptyArguments, self._dataset_summary),
            "get_issue_group": (IssueGroupArguments, self._issue_group),
            "get_representative_issues": (
                RepresentativeIssuesArguments,
                self._representative_issues,
            ),
            "get_class_distribution": (
                ClassDistributionArguments,
                self._class_distribution,
            ),
            "get_score_component": (
                ScoreComponentArguments,
                self._score_component,
            ),
            "get_duplicate_summary": (
                DuplicateSummaryArguments,
                self._duplicate_summary,
            ),
            "get_split_leakage_summary": (
                SplitLeakageArguments,
                self._split_leakage,
            ),
            "get_repair_simulations": (
                RepairSimulationsArguments,
                self._repair_simulations,
            ),
        }

    def tool_definitions(self) -> list[dict[str, Any]]:
        """Return a stable OpenAI-compatible function allowlist."""

        descriptions = {
            "get_dataset_summary": "Return bounded dataset and issue totals.",
            "get_issue_group": "Return aggregate facts for one exact Issue code.",
            "get_representative_issues": "Return a bounded issue evidence sample.",
            "get_class_distribution": "Return bounded per-class instance facts.",
            "get_score_component": "Return one Health Score component and penalty.",
            "get_duplicate_summary": "Return bounded exact/near duplicate facts.",
            "get_split_leakage_summary": "Return bounded cross-split leakage facts.",
            "get_repair_simulations": "Return bounded hypothetical repair previews.",
        }
        definitions = []
        for name in TOOL_NAMES:
            arguments_model = self._registry[name][0]
            definitions.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": descriptions[name],
                        "parameters": arguments_model.model_json_schema(),
                        "strict": True,
                    },
                }
            )
        return definitions

    def execute_json_arguments(self, name: str, arguments_json: str) -> str:
        """Validate model-supplied JSON and return one size-bounded result."""

        try:
            payload = json.loads(arguments_json)
        except (json.JSONDecodeError, TypeError):
            raise EvidenceToolArgumentsError from None
        if not isinstance(payload, dict):
            raise EvidenceToolArgumentsError
        return self.execute(name, payload)

    def execute(self, name: str, arguments: Mapping[str, object]) -> str:
        """Execute one allowlisted query without filesystem or network access."""

        registered = self._registry.get(name)
        if registered is None:
            raise UnknownEvidenceToolError
        arguments_model, handler = registered
        try:
            validated = arguments_model.model_validate(dict(arguments))
        except ValidationError:
            raise EvidenceToolArgumentsError from None
        response = handler(validated)
        serialized = stable_json(response)
        if len(serialized.encode("utf-8")) > self._max_result_bytes:
            raise EvidenceLimitError
        return serialized

    def _dataset_summary(self, arguments: QueryArguments) -> dict[str, Any]:
        del arguments
        severity_counts = Counter(issue.severity.value for issue in self._report.issues)
        knowledge = self._report.knowledge_guidance
        return {
            "source_tool": "get_dataset_summary",
            "summary": self._report.manifest.summary.model_dump(mode="json"),
            "severity_counts": {
                name: severity_counts[name]
                for name in ("critical", "error", "warning", "info")
            },
            "health_score": self._report.health_score.overall,
            "health_grade": self._report.health_score.grade,
            "score_profile": self._report.health_score.profile_name,
            "available_issue_codes": sorted(
                {issue.code for issue in self._report.issues}
            )[: self._max_items],
            "available_issue_code_count": len(
                {issue.code for issue in self._report.issues}
            ),
            "knowledge_guidance": (
                {
                    "profile_id": knowledge.profile_id.value,
                    "pack_schema_version": knowledge.pack_schema_version,
                    "advisory_notice": knowledge.advisory_notice,
                    "guidance_entries": [
                        {
                            "guidance_id": entry.guidance_id,
                            "title": entry.title,
                            "guidance": entry.guidance,
                            "requires_human_confirmation": (
                                entry.requires_human_confirmation
                            ),
                        }
                        for entry in knowledge.guidance_entries[: self._max_items]
                    ],
                }
                if knowledge is not None
                else None
            ),
        }

    def _issue_group(self, arguments: QueryArguments) -> dict[str, Any]:
        query = cast(IssueGroupArguments, arguments)
        members = [
            issue for issue in self._report.issues if issue.code == query.code
        ]
        affected = {
            issue.image_id or issue.relative_path or issue.issue_id for issue in members
        }
        severity = (
            max(members, key=lambda item: _SEVERITY_RANK[item.severity]).severity.value
            if members
            else None
        )
        return {
            "source_tool": "get_issue_group",
            "code": query.code,
            "count": len(members),
            "affected_count": len(affected),
            "severity": severity,
            "representative_issue_ids": [
                issue.issue_id
                for issue in sorted(members, key=lambda item: item.issue_id)[
                    : self._max_items
                ]
            ],
            "truncated": len(members) > self._max_items,
        }

    def _representative_issues(self, arguments: QueryArguments) -> dict[str, Any]:
        query = cast(RepresentativeIssuesArguments, arguments)
        maximum = min(query.limit, self._max_items)
        issues = [
            issue
            for issue in self._report.issues
            if (query.code is None or issue.code == query.code)
            and (query.severity is None or issue.severity == query.severity)
        ]
        issues.sort(
            key=lambda issue: (
                -_SEVERITY_RANK[issue.severity],
                issue.code,
                issue.issue_id,
            )
        )
        return {
            "source_tool": "get_representative_issues",
            "items": [self._issue_evidence(issue) for issue in issues[:maximum]],
            "matched_count": len(issues),
            "returned_count": min(len(issues), maximum),
            "truncated": len(issues) > maximum,
        }

    @staticmethod
    def _issue_evidence(issue: Issue) -> dict[str, Any]:
        numeric_metrics = {
            key: value
            for key, value in sorted(issue.metrics.items())
            if isinstance(value, int | float) and not isinstance(value, bool)
        }
        return {
            "issue_id": issue.issue_id,
            "code": issue.code,
            "severity": issue.severity.value,
            "relative_path_untrusted": issue.relative_path,
            "annotation_line": issue.annotation_line,
            "bbox": list(issue.bbox) if issue.bbox is not None else None,
            "numeric_metrics": numeric_metrics,
        }

    def _class_distribution(self, arguments: QueryArguments) -> dict[str, Any]:
        query = cast(ClassDistributionArguments, arguments)
        maximum = min(query.limit, self._max_items)
        all_ids = sorted(self._report.distribution.class_counts)
        selected = (
            [class_id for class_id in query.class_ids if class_id in all_ids]
            if query.class_ids is not None
            else all_ids
        )
        selected = selected[:maximum]
        return {
            "source_tool": "get_class_distribution",
            "classes": [
                {
                    "class_id": class_id,
                    "class_name_untrusted": self._report.manifest.class_names.get(
                        class_id,
                        "Unknown",
                    ),
                    "instance_count": self._report.distribution.class_counts.get(
                        class_id,
                        0,
                    ),
                    "image_count": self._report.distribution.class_image_counts.get(
                        class_id,
                        0,
                    ),
                    "is_rare": class_id in self._report.distribution.rare_class_ids,
                    "is_zero": (
                        class_id
                        in self._report.distribution.zero_instance_class_ids
                    ),
                }
                for class_id in selected
            ],
            "class_count": len(all_ids),
            "returned_count": len(selected),
            "truncated": len(all_ids) > len(selected),
            "imbalance_index": self._report.distribution.imbalance_index,
        }

    def _score_component(self, arguments: QueryArguments) -> dict[str, Any]:
        query = cast(ScoreComponentArguments, arguments)
        return {
            "source_tool": "get_score_component",
            "component": query.component,
            "overall": self._report.health_score.overall,
            "grade": self._report.health_score.grade,
            "raw_ratio": self._report.health_score.raw_ratios[query.component],
            "penalty": self._report.health_score.penalties[query.component],
            "penalty_cap": self._report.health_score.penalty_caps[query.component],
            "profile_name": self._report.health_score.profile_name,
            "methodology_version": self._report.health_score.methodology_version,
        }

    def _duplicate_summary(self, arguments: QueryArguments) -> dict[str, Any]:
        query = cast(DuplicateSummaryArguments, arguments)
        maximum = min(query.limit, self._max_items)
        groups = [
            group
            for group in self._report.duplicate_groups
            if query.kind == "all" or group.kind == query.kind
        ]
        groups.sort(key=lambda group: (group.kind, group.group_id))
        counts = Counter(group.kind for group in self._report.duplicate_groups)
        return {
            "source_tool": "get_duplicate_summary",
            "exact_group_count": counts["exact"],
            "near_group_count": counts["near"],
            "matched_group_count": len(groups),
            "groups": [
                {
                    "group_id": group.group_id,
                    "kind": group.kind,
                    "member_count": len(group.image_ids),
                    "representative_path_untrusted": (
                        group.representative_image_id
                    ),
                    "sample_member_paths_untrusted": group.image_ids[:2],
                    "hamming_distance": group.hamming_distance,
                }
                for group in groups[:maximum]
            ],
            "truncated": len(groups) > maximum,
        }

    def _split_leakage(self, arguments: QueryArguments) -> dict[str, Any]:
        query = cast(SplitLeakageArguments, arguments)
        maximum = min(query.limit, self._max_items)
        allowed_codes = {
            "exact": {"SPLIT_LEAKAGE_EXACT"},
            "near": {"SPLIT_LEAKAGE_NEAR"},
            "all": {"SPLIT_LEAKAGE_EXACT", "SPLIT_LEAKAGE_NEAR"},
        }[query.kind]
        issues = [
            issue for issue in self._report.issues if issue.code in allowed_codes
        ]
        issues.sort(key=lambda issue: (issue.code, issue.issue_id))
        exact_groups = {
            issue.evidence.get("duplicate_group_id")
            for issue in issues
            if issue.code == "SPLIT_LEAKAGE_EXACT"
        }
        near_groups = {
            issue.evidence.get("duplicate_group_id")
            for issue in issues
            if issue.code == "SPLIT_LEAKAGE_NEAR"
        }
        exact_groups.discard(None)
        near_groups.discard(None)
        return {
            "source_tool": "get_split_leakage_summary",
            "exact_group_count": len(exact_groups),
            "near_group_count": len(near_groups),
            "matched_group_count": len(exact_groups | near_groups),
            "items": [
                {
                    "issue_id": issue.issue_id,
                    "code": issue.code,
                    "severity": issue.severity.value,
                    "representative_path_untrusted": issue.relative_path,
                    "duplicate_group_id": issue.evidence.get(
                        "duplicate_group_id"
                    ),
                    "splits": issue.metrics.get("splits", []),
                    "image_count": issue.metrics.get("image_count", 0),
                    "hamming_distance": issue.metrics.get(
                        "hamming_distance"
                    ),
                }
                for issue in issues[:maximum]
            ],
            "truncated": len(issues) > maximum,
        }

    def _repair_simulations(self, arguments: QueryArguments) -> dict[str, Any]:
        query = cast(RepairSimulationsArguments, arguments)
        maximum = min(query.limit, self._max_items)
        impacts = (
            self._report.repair_simulation.impacts
            if self._report.repair_simulation is not None
            else []
        )
        return {
            "source_tool": "get_repair_simulations",
            "items": [
                {
                    "scenario_id": impact.scenario.scenario_id,
                    "title": impact.scenario.title,
                    "estimated_effort": impact.scenario.estimated_effort,
                    "current_score": impact.original_score,
                    "simulated_score": impact.simulated_score,
                    "score_delta": impact.score_delta,
                    "affected_issue_count": impact.affected_issue_count,
                    "requires_human_confirmation": (
                        impact.scenario.requires_human_confirmation
                    ),
                    "hypothetical_only": True,
                }
                for impact in impacts[:maximum]
            ],
            "available_count": len(impacts),
            "returned_count": min(len(impacts), maximum),
            "truncated": len(impacts) > maximum,
        }


__all__ = [
    "TOOL_NAMES",
    "EvidenceLimitError",
    "EvidenceQueryService",
    "EvidenceToolArgumentsError",
    "EvidenceToolError",
    "UnknownEvidenceToolError",
    "stable_json",
]
