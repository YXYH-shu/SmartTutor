"""Stable, privacy-safe text representations for graph nodes."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any, Iterable

from algorithm.graph_recommender.data.types import EmbeddingKey, GraphRows

TEXT_TEMPLATE_VERSION = "v1"


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    if isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (list, tuple, set)):
        values = [_clean(item) for item in value]
        return [item for item in values if item is not None]
    if isinstance(value, dict):
        return {
            str(key): cleaned
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if (cleaned := _clean(item)) is not None
        }
    return str(value)


def _render(entity_type: str, values: dict[str, Any]) -> str:
    payload = {key: cleaned for key, value in values.items() if (cleaned := _clean(value)) is not None}
    return json.dumps({"type": entity_type, **payload}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _coverage_ids(raw: Any) -> set[str]:
    if isinstance(raw, dict):
        return {str(key) for key in raw}
    if isinstance(raw, (list, tuple, set)):
        result = set()
        for item in raw:
            if isinstance(item, dict):
                for key in ("id", "kp_id", "knowledge_id"):
                    if item.get(key) is not None:
                        result.add(str(item[key]))
                        break
            elif item is not None:
                result.add(str(item))
        return result
    return set()


def _predecessor_ids(raw: Any) -> set[str]:
    return _coverage_ids(raw)


def build_node_texts(
    rows: GraphRows,
    keys: Iterable[EmbeddingKey] | None = None,
) -> dict[str, dict[str, str]]:
    """Return deterministic text for every graph node without identity fields."""

    requested = None
    if keys is not None:
        requested = defaultdict(set)
        for key in keys:
            requested[key.entity_type].add(key.entity_id)

    def include(entity_type: str, entity_id: str) -> bool:
        return requested is None or entity_id in requested[entity_type]

    knowledge_names = {point.id: point.name for point in rows.knowledge_points}
    resource_knowledge: dict[str, set[str]] = defaultdict(set)
    for link in rows.resource_knowledge:
        resource_knowledge[link.resource_id].add(link.knowledge_id)
    predecessors: dict[str, set[str]] = defaultdict(set)
    for link in rows.knowledge_prerequisites:
        predecessors[link.target_id].add(link.source_id)

    learner_texts = {
        learner.id: _render(
            "learner",
            {
                "learning_style": learner.profile.get("learning_style"),
                "current_level": learner.profile.get("current_level"),
                "grade_level": learner.profile.get("grade_level"),
                "weak_points": learner.profile.get("weak_points"),
                "preferences": learner.profile.get("preferences"),
                "knowledge_state": {
                    knowledge_names[knowledge_id]: value
                    for knowledge_id, value in learner.knowledge_graph.items()
                    if knowledge_id in knowledge_names
                },
            },
        )
        for learner in rows.learners
        if include("learner", learner.id)
    }
    resource_texts: dict[str, str] = {}
    for resource in rows.resources:
        if not include("resource", resource.id):
            continue
        covered_ids = resource_knowledge.get(resource.id) or _coverage_ids(resource.knowledge_coverage)
        resource_texts[resource.id] = _render(
            "resource",
            {
                "name": resource.name,
                "content": resource.content,
                "resource_type": resource.resource_type,
                "difficulty": resource.difficult,
                "estimated_minutes": resource.time_need,
                "knowledge_points": sorted(
                    knowledge_names[knowledge_id]
                    for knowledge_id in covered_ids
                    if knowledge_id in knowledge_names
                ),
            },
        )
    knowledge_texts: dict[str, str] = {}
    for point in rows.knowledge_points:
        if not include("knowledge_point", point.id):
            continue
        predecessor_ids = predecessors.get(point.id) or _predecessor_ids(point.pre_knowledge)
        knowledge_texts[point.id] = _render(
            "knowledge_point",
            {
                "name": point.name,
                "content": point.content,
                "subject": point.subject,
                "grade": point.grade,
                "grade_level": point.grade_level,
                "cognitive_level": point.cognitive_level,
                "difficulty": point.difficult,
                "prerequisites": sorted(
                    knowledge_names[knowledge_id]
                    for knowledge_id in predecessor_ids
                    if knowledge_id in knowledge_names
                ),
            },
        )
    return {
        "learner": learner_texts,
        "resource": resource_texts,
        "knowledge_point": knowledge_texts,
    }
