"""Data-quality checks run before costly embedding generation or training."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict

from .types import GraphRows


def audit_rows(rows: GraphRows) -> dict[str, object]:
    learner_ids = {row.id for row in rows.learners}
    resource_ids = {row.id for row in rows.resources}
    knowledge_ids = {row.id for row in rows.knowledge_points}

    def orphan_count(pairs, left, right):
        return sum(source not in left or target not in right for source, target in pairs)

    resource_pairs = [(row.learner_id, row.resource_id) for row in rows.resource_interactions]
    resource_knowledge_pairs = [(row.resource_id, row.knowledge_id) for row in rows.resource_knowledge]
    state_pairs = [(row.learner_id, row.knowledge_id) for row in rows.knowledge_states]
    prerequisite_pairs = [(row.source_id, row.target_id) for row in rows.knowledge_prerequisites]
    partner_pairs = [tuple(sorted((row.learner_a_id, row.learner_b_id))) for row in rows.partner_relations]

    return {
        "nodes": {
            "learners": len(learner_ids),
            "resources": len(resource_ids),
            "knowledge_points": len(knowledge_ids),
        },
        "edges": {
            "learner_resource": len(resource_pairs),
            "resource_knowledge": len(resource_knowledge_pairs),
            "learner_knowledge": len(state_pairs),
            "knowledge_knowledge": len(prerequisite_pairs),
            "learner_learner": len(partner_pairs),
        },
        "duplicates": {
            "learner_resource": len(resource_pairs) - len(set(resource_pairs)),
            "resource_knowledge": len(resource_knowledge_pairs) - len(set(resource_knowledge_pairs)),
            "learner_knowledge": len(state_pairs) - len(set(state_pairs)),
            "knowledge_knowledge": len(prerequisite_pairs) - len(set(prerequisite_pairs)),
            "learner_learner": len(partner_pairs) - len(set(partner_pairs)),
        },
        "orphans": {
            "learner_resource": orphan_count(resource_pairs, learner_ids, resource_ids),
            "resource_knowledge": orphan_count(resource_knowledge_pairs, resource_ids, knowledge_ids),
            "learner_knowledge": orphan_count(state_pairs, learner_ids, knowledge_ids),
            "knowledge_knowledge": orphan_count(prerequisite_pairs, knowledge_ids, knowledge_ids),
            "learner_learner": orphan_count(partner_pairs, learner_ids, learner_ids),
        },
        "missing_timestamps": {
            "learner_resource": sum(row.created_at is None for row in rows.resource_interactions),
            "learner_knowledge": sum(row.created_at is None for row in rows.knowledge_states),
            "learner_learner": sum(row.created_at is None for row in rows.partner_relations),
        },
        "warnings": [
            warning
            for warning, condition in (
                ("no learner-resource interactions available for resource training", not resource_pairs),
                ("no learner-learner relations available for peer training", not partner_pairs),
                ("no resource-knowledge links available", not resource_knowledge_pairs),
            )
            if condition
        ],
    }
