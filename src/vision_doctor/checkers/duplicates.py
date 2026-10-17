"""Exact and perceptual duplicate grouping for small MVP datasets."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

from vision_doctor.config import DuplicateDetectionConfig
from vision_doctor.models import DatasetManifest, DuplicateGroup, ImageRecord
from vision_doctor.utils.images import decode_image, hamming_distance, perceptual_hash


def _sha256(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _group_id(kind: str, image_ids: list[str]) -> str:
    payload = json.dumps([kind, image_ids], separators=(",", ":"))
    return f"duplicate-{hashlib.sha256(payload.encode()).hexdigest()[:20]}"


def _components(nodes: list[str], edges: list[tuple[str, str]]) -> list[list[str]]:
    neighbors: dict[str, set[str]] = {node: set() for node in nodes}
    for first, second in edges:
        neighbors[first].add(second)
        neighbors[second].add(first)
    result: list[list[str]] = []
    visited: set[str] = set()
    for node in nodes:
        if node in visited or not neighbors[node]:
            continue
        pending = [node]
        component: list[str] = []
        visited.add(node)
        while pending:
            current = pending.pop()
            component.append(current)
            for neighbor in sorted(neighbors[current]):
                if neighbor not in visited:
                    visited.add(neighbor)
                    pending.append(neighbor)
        result.append(sorted(component))
    return result


def find_duplicate_groups(
    manifest: DatasetManifest,
    dataset_root: str | Path,
    *,
    config: DuplicateDetectionConfig | None = None,
) -> list[DuplicateGroup]:
    """Return deterministic exact and near groups using bounded O(n^2) matching."""

    active = config or DuplicateDetectionConfig()
    records = sorted(manifest.images, key=lambda item: item.image_id)
    if len(records) > active.max_images_for_pairwise:
        raise ValueError(
            "Pairwise duplicate detection supports at most "
            f"{active.max_images_for_pairwise} images with the current configuration."
        )
    root = Path(dataset_root)
    hashes: dict[str, str] = {}
    exact_buckets: dict[str, list[str]] = defaultdict(list)
    records_by_id: dict[str, ImageRecord] = {}
    for record in records:
        records_by_id[record.image_id] = record
        digest = record.sha256 or _sha256(root / Path(record.relative_path))
        if digest is not None:
            hashes[record.image_id] = digest
            exact_buckets[digest].append(record.image_id)

    exact_groups: list[DuplicateGroup] = []
    representatives: list[str] = []
    for image_ids in exact_buckets.values():
        ordered = sorted(image_ids)
        representatives.append(ordered[0])
        if len(ordered) > 1:
            exact_groups.append(
                DuplicateGroup(
                    group_id=_group_id("exact", ordered),
                    kind="exact",
                    image_ids=ordered,
                    representative_image_id=ordered[0],
                    hamming_distance=0,
                )
            )

    phashes: dict[str, int] = {}
    for image_id in sorted(representatives):
        record = records_by_id[image_id]
        image = decode_image(root / Path(record.relative_path))
        if image is not None:
            phashes[image_id] = perceptual_hash(
                image, hash_size=active.perceptual_hash_size
            )

    near_edges: list[tuple[str, str]] = []
    distances: dict[tuple[str, str], int] = {}
    image_ids = sorted(phashes)
    for index, first in enumerate(image_ids):
        for second in image_ids[index + 1 :]:
            if hashes.get(first) == hashes.get(second):
                continue
            distance = hamming_distance(phashes[first], phashes[second])
            if distance <= active.near_duplicate_hamming_threshold:
                pair = (first, second)
                near_edges.append(pair)
                distances[pair] = distance

    near_groups: list[DuplicateGroup] = []
    for component in _components(image_ids, near_edges):
        component_pairs = {
            f"{first}|{second}": distance
            for (first, second), distance in distances.items()
            if first in component and second in component
        }
        near_groups.append(
            DuplicateGroup(
                group_id=_group_id("near", component),
                kind="near",
                image_ids=component,
                representative_image_id=component[0],
                hamming_distance=max(component_pairs.values()),
                pair_distances=component_pairs,
            )
        )
    return sorted(exact_groups + near_groups, key=lambda group: (group.kind, group.group_id))
