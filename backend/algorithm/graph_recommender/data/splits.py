"""Leakage-safe temporal splits for resource and peer ranking tasks."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from .types import PartnerRelation, ResourceInteraction


def _time_key(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


@dataclass(frozen=True)
class LinkSplits:
    train: set[tuple[str, str]]
    validation: set[tuple[str, str]]
    test: set[tuple[str, str]]

    @property
    def all_positive(self) -> set[tuple[str, str]]:
        return self.train | self.validation | self.test


def split_resource_interactions(interactions: list[ResourceInteraction]) -> LinkSplits:
    """Hold out a learner's latest two unique resources for validation and test."""
    latest: dict[tuple[str, str], datetime] = {}
    for interaction in interactions:
        key = (interaction.learner_id, interaction.resource_id)
        timestamp = _time_key(interaction.created_at)
        if timestamp >= latest.get(key, datetime.min.replace(tzinfo=timezone.utc)):
            latest[key] = timestamp
    per_learner: dict[str, list[tuple[datetime, str]]] = defaultdict(list)
    for (learner_id, resource_id), timestamp in latest.items():
        per_learner[learner_id].append((timestamp, resource_id))

    train: set[tuple[str, str]] = set()
    validation: set[tuple[str, str]] = set()
    test: set[tuple[str, str]] = set()
    for learner_id, entries in per_learner.items():
        entries.sort(key=lambda pair: (pair[0], pair[1]))
        if len(entries) < 3:
            train.update((learner_id, resource_id) for _, resource_id in entries)
            continue
        train.update((learner_id, resource_id) for _, resource_id in entries[:-2])
        validation.add((learner_id, entries[-2][1]))
        test.add((learner_id, entries[-1][1]))
    return LinkSplits(train=train, validation=validation, test=test)


def split_peer_relations(relations: list[PartnerRelation]) -> LinkSplits:
    """Split canonical undirected relations globally in chronological order."""
    first_seen: dict[tuple[str, str], datetime] = {}
    for relation in relations:
        if relation.learner_a_id == relation.learner_b_id:
            continue
        pair = tuple(sorted((relation.learner_a_id, relation.learner_b_id)))
        timestamp = _time_key(relation.created_at)
        current = first_seen.get(pair)
        if current is None or timestamp < current:
            first_seen[pair] = timestamp
    ordered = sorted(((timestamp, pair) for pair, timestamp in first_seen.items()), key=lambda row: (row[0], row[1]))
    if len(ordered) < 3:
        return LinkSplits({pair for _, pair in ordered}, set(), set())
    count = len(ordered)
    train_end = max(1, int(count * 0.8))
    validation_end = max(train_end, int(count * 0.9))
    validation_end = min(validation_end, count - 1)
    return LinkSplits(
        train={pair for _, pair in ordered[:train_end]},
        validation={pair for _, pair in ordered[train_end:validation_end]},
        test={pair for _, pair in ordered[validation_end:]},
    )
