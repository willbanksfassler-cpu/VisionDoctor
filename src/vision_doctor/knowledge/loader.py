"""Load only allowlisted, package-local knowledge YAML files."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from vision_doctor.models import KnowledgePack, KnowledgeProfile

_PACK_DIRECTORY = Path(__file__).resolve().parent / "packs"
_PACK_FILENAMES: dict[KnowledgeProfile, str] = {
    KnowledgeProfile.GENERIC: "generic.yaml",
    KnowledgeProfile.INDUSTRIAL_INSPECTION: "industrial_inspection.yaml",
    KnowledgeProfile.RETAIL_DETECTION: "retail_detection.yaml",
    KnowledgeProfile.SMALL_OBJECT_DETECTION: "small_object_detection.yaml",
}


class KnowledgePackLoadError(ValueError):
    """A local, allowlisted knowledge pack failed safe validation."""


def resolve_knowledge_profile(
    profile: KnowledgeProfile | str,
    *,
    fallback_to_generic: bool = True,
) -> tuple[KnowledgeProfile, str | None]:
    """Resolve an enum value without ever interpreting it as a path."""

    try:
        return KnowledgeProfile(profile), None
    except ValueError:
        if fallback_to_generic:
            return KnowledgeProfile.GENERIC, "unknown_profile"
        raise KnowledgePackLoadError("unknown knowledge profile") from None


def load_knowledge_pack(
    profile: KnowledgeProfile | str,
    *,
    fallback_to_generic: bool = True,
) -> KnowledgePack:
    """Load one fixed pack with safe YAML parsing and strict Pydantic validation."""

    selected, _ = resolve_knowledge_profile(
        profile,
        fallback_to_generic=fallback_to_generic,
    )
    path = _PACK_DIRECTORY / _PACK_FILENAMES[selected]
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise KnowledgePackLoadError("knowledge pack root must be an object")
        pack = KnowledgePack.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as error:
        raise KnowledgePackLoadError("knowledge pack could not be validated") from error
    if pack.profile_id is not selected:
        raise KnowledgePackLoadError("knowledge pack profile does not match its registry")
    return pack


def load_all_knowledge_packs() -> dict[KnowledgeProfile, KnowledgePack]:
    """Validate every registered pack and return it in stable enum order."""

    return {
        profile: load_knowledge_pack(profile, fallback_to_generic=False)
        for profile in KnowledgeProfile
    }
