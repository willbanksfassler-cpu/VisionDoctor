"""Deterministic class-frequency and image-coverage statistics."""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict

from vision_doctor.models import DatasetManifest, DistributionStats


def calculate_distribution(manifest: DatasetManifest) -> DistributionStats:
    """Calculate instance counts, image coverage, rarity, and imbalance."""

    declared_ids = sorted(manifest.class_names)
    instance_counts = Counter(annotation.class_id for annotation in manifest.annotations)
    images_by_class: dict[int, set[str]] = defaultdict(set)
    for annotation in manifest.annotations:
        images_by_class[annotation.class_id].add(annotation.image_id)

    class_counts = {class_id: instance_counts[class_id] for class_id in declared_ids}
    class_image_counts = {
        class_id: len(images_by_class[class_id]) for class_id in declared_ids
    }
    total = sum(class_counts.values())
    percentages = {
        class_id: count / total if total else 0.0
        for class_id, count in class_counts.items()
    }
    zero_ids = [class_id for class_id, count in class_counts.items() if count == 0]
    nonzero_counts = [count for count in class_counts.values() if count > 0]
    rare_threshold = (
        max(10.0, 0.2 * statistics.median(nonzero_counts))
        if nonzero_counts
        else 10.0
    )
    rare_ids = [
        class_id
        for class_id, count in class_counts.items()
        if 0 < count < rare_threshold
    ]
    if len(nonzero_counts) <= 1:
        imbalance_index = 1.0 if nonzero_counts else None
    else:
        imbalance_index = max(nonzero_counts) / min(nonzero_counts)

    return DistributionStats(
        total_annotations=total,
        class_counts=class_counts,
        class_image_counts=class_image_counts,
        class_percentages=percentages,
        imbalance_ratio=imbalance_index,
        imbalance_index=imbalance_index,
        rare_class_ids=rare_ids,
        missing_class_ids=zero_ids,
        zero_instance_class_ids=zero_ids,
        rare_class_threshold=rare_threshold,
    )
