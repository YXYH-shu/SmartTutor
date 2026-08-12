"""Database-independent records used by graph construction and training."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

EntityType = Literal["learner", "resource", "knowledge_point"]
ChangeOperation = Literal["upsert", "delete"]


@dataclass(frozen=True)
class LearnerRecord:
    id: str
    profile: dict[str, Any] = field(default_factory=dict)
    knowledge_graph: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResourceRecord:
    id: str
    name: str
    content: str | None = None
    resource_type: str | None = None
    difficult: float | None = None
    time_need: int | None = None
    knowledge_coverage: Any = None


@dataclass(frozen=True)
class KnowledgePointRecord:
    id: str
    name: str
    content: str | None = None
    subject: str | None = None
    grade: str | None = None
    pre_knowledge: Any = None
    difficult: float | None = None
    grade_level: str | None = None
    cognitive_level: str | None = None


@dataclass(frozen=True)
class ResourceInteraction:
    learner_id: str
    resource_id: str
    created_at: datetime | None = None


@dataclass(frozen=True)
class ResourceKnowledgeLink:
    resource_id: str
    knowledge_id: str


@dataclass(frozen=True)
class KnowledgeStateLink:
    learner_id: str
    knowledge_id: str
    learn_score: float | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class KnowledgePrerequisiteLink:
    source_id: str
    target_id: str


@dataclass(frozen=True)
class PartnerRelation:
    learner_a_id: str
    learner_b_id: str
    created_at: datetime | None = None


@dataclass
class GraphRows:
    learners: list[LearnerRecord] = field(default_factory=list)
    resources: list[ResourceRecord] = field(default_factory=list)
    knowledge_points: list[KnowledgePointRecord] = field(default_factory=list)
    resource_interactions: list[ResourceInteraction] = field(default_factory=list)
    resource_knowledge: list[ResourceKnowledgeLink] = field(default_factory=list)
    knowledge_states: list[KnowledgeStateLink] = field(default_factory=list)
    knowledge_prerequisites: list[KnowledgePrerequisiteLink] = field(default_factory=list)
    partner_relations: list[PartnerRelation] = field(default_factory=list)


@dataclass(frozen=True)
class GraphChange:
    """A post-commit notification describing authoritative database changes."""

    operation: ChangeOperation
    entity_type: EntityType | Literal["edge"]
    entity_id: str | None = None
    relation_type: str | None = None
    source_id: str | None = None
    target_id: str | None = None
    sequence: int | None = None


@dataclass(frozen=True)
class EmbeddingKey:
    entity_type: EntityType
    entity_id: str


@dataclass(frozen=True)
class CachedEmbedding:
    key: EmbeddingKey
    model_id: str
    template_version: str
    text_hash: str
    dimension: int
    vector: list[float]
