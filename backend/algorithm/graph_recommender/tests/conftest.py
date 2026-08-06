from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from algorithm.graph_recommender.data.types import (
    GraphRows,
    KnowledgePointRecord,
    KnowledgePrerequisiteLink,
    KnowledgeStateLink,
    LearnerRecord,
    PartnerRelation,
    ResourceInteraction,
    ResourceKnowledgeLink,
    ResourceRecord,
)


@pytest.fixture
def graph_rows() -> GraphRows:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return GraphRows(
        learners=[
            LearnerRecord(
                "u1",
                {"learning_style": "visual", "current_level": "basic", "weak_points": ["k2"]},
                {"k1": 0.8},
            ),
            LearnerRecord("u2", {"learning_style": "practice"}),
            LearnerRecord("u3", {}),
        ],
        resources=[
            ResourceRecord("r1", "resource one", knowledge_coverage={"k1": 1}),
            ResourceRecord("r2", "resource two", knowledge_coverage=["k2"]),
            ResourceRecord("r3", "resource three"),
        ],
        knowledge_points=[
            KnowledgePointRecord("k1", "knowledge one"),
            KnowledgePointRecord("k2", "knowledge two", pre_knowledge=["k1"]),
        ],
        resource_interactions=[
            ResourceInteraction("u1", "r1", now),
            ResourceInteraction("u1", "r2", now + timedelta(days=1)),
            ResourceInteraction("u1", "r3", now + timedelta(days=2)),
            ResourceInteraction("u1", "r3", now + timedelta(days=3)),
        ],
        resource_knowledge=[ResourceKnowledgeLink("r1", "k1")],
        knowledge_states=[KnowledgeStateLink("u2", "k2", 0.2, now)],
        knowledge_prerequisites=[],
        partner_relations=[
            PartnerRelation("u1", "u2", now),
            PartnerRelation("u2", "u1", now + timedelta(days=1)),
            PartnerRelation("u1", "u3", now + timedelta(days=2)),
            PartnerRelation("u2", "u3", now + timedelta(days=3)),
        ],
    )
