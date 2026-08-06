"""Repository adapters for current SQLAlchemy models and deterministic tests."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any, Protocol

from .types import (
    CachedEmbedding,
    EmbeddingKey,
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


class GraphRepository(Protocol):
    async def load_rows(self) -> GraphRows: ...

    async def load_embeddings(
        self,
        keys: Iterable[EmbeddingKey],
        model_id: str,
        template_version: str,
    ) -> dict[EmbeddingKey, CachedEmbedding]: ...

    async def upsert_embeddings(self, records: Iterable[CachedEmbedding]) -> None: ...

    async def delete_embeddings(self, keys: Iterable[EmbeddingKey]) -> None: ...


class SqlAlchemyGraphRepository:
    """Async repository backed by the application's SQLAlchemy session factory."""

    def __init__(self, session_factory: Callable[..., Any] | None = None):
        self._session_factory = session_factory

    def _new_session(self):
        if self._session_factory is None:
            from app.database import AsyncSessionLocal

            return AsyncSessionLocal()
        return self._session_factory()

    async def load_rows(self) -> GraphRows:
        from sqlalchemy import select

        from app.models.knowledge_knowledge import KnowledgeKnowledge
        from app.models.knowledge_point import KnowledgePoint
        from app.models.learner_interaction import (
            LearnerKnowledgeInteraction,
            LearnerLearnerRelation,
            LearnerResourceInteraction,
        )
        from app.models.learning_resource import LearningResource
        from app.models.resource_knowledge import ResourceKnowledge
        from app.models.user import User
        from app.models.user_profile import UserProfile

        async with self._new_session() as session:
            learner_result = await session.execute(
                select(User, UserProfile).outerjoin(UserProfile, UserProfile.user_id == User.id)
            )
            learners = []
            for user, profile in learner_result.all():
                profile_values = {
                    "learning_style": getattr(profile, "learning_style", None),
                    "current_level": getattr(profile, "current_level", None),
                    "grade_level": getattr(profile, "grade_level", None),
                    "weak_points": getattr(profile, "weak_points", None),
                    "preferences": getattr(profile, "preferences", None),
                }
                knowledge_graph = getattr(profile, "knowledge_graph", None) or {}
                learners.append(
                    LearnerRecord(str(user.id), profile_values, knowledge_graph)
                )

            resources = [
                ResourceRecord(
                    id=str(row.id),
                    name=row.name,
                    content=row.content,
                    resource_type=row.type,
                    difficult=row.difficult,
                    time_need=row.time_need,
                    knowledge_coverage=row.knowledge_coverage,
                )
                for row in (await session.execute(select(LearningResource))).scalars().all()
            ]
            knowledge_points = [
                KnowledgePointRecord(
                    id=str(row.id),
                    name=row.name,
                    content=row.content,
                    subject=row.subject,
                    grade=row.grade,
                    pre_knowledge=row.pre_knowledge,
                    difficult=row.difficult,
                    grade_level=getattr(row, "grade_level", None),
                    cognitive_level=getattr(row, "cognitive_level", None),
                )
                for row in (await session.execute(select(KnowledgePoint))).scalars().all()
            ]
            resource_interactions = [
                ResourceInteraction(str(row.learner_id), str(row.resource_id), row.created_at)
                for row in (await session.execute(select(LearnerResourceInteraction))).scalars().all()
            ]
            resource_knowledge = [
                ResourceKnowledgeLink(str(row.resource_id), str(row.kp_id))
                for row in (await session.execute(select(ResourceKnowledge))).scalars().all()
            ]
            knowledge_states = [
                KnowledgeStateLink(
                    str(row.learner_id), str(row.knowledge_id), row.learn_score, row.created_at
                )
                for row in (await session.execute(select(LearnerKnowledgeInteraction))).scalars().all()
            ]
            prerequisites = [
                KnowledgePrerequisiteLink(str(row.source_kp_id), str(row.target_kp_id))
                for row in (await session.execute(select(KnowledgeKnowledge))).scalars().all()
            ]
            partner_relations = [
                PartnerRelation(str(row.learner_a_id), str(row.learner_b_id), row.created_at)
                for row in (await session.execute(select(LearnerLearnerRelation))).scalars().all()
            ]

        return GraphRows(
            learners=learners,
            resources=resources,
            knowledge_points=knowledge_points,
            resource_interactions=resource_interactions,
            resource_knowledge=resource_knowledge,
            knowledge_states=knowledge_states,
            knowledge_prerequisites=prerequisites,
            partner_relations=partner_relations,
        )

    async def load_embeddings(
        self,
        keys: Iterable[EmbeddingKey],
        model_id: str,
        template_version: str,
    ) -> dict[EmbeddingKey, CachedEmbedding]:
        from sqlalchemy import select, tuple_

        from app.models.graph_node_embedding import GraphNodeEmbedding

        key_list = list(keys)
        if not key_list:
            return {}
        pairs = [(key.entity_type, key.entity_id) for key in key_list]
        async with self._new_session() as session:
            result = await session.execute(
                select(GraphNodeEmbedding).where(
                    tuple_(GraphNodeEmbedding.entity_type, GraphNodeEmbedding.entity_id).in_(pairs),
                    GraphNodeEmbedding.embedding_model_id == model_id,
                    GraphNodeEmbedding.text_template_version == template_version,
                )
            )
            rows = result.scalars().all()
        return {
            EmbeddingKey(row.entity_type, row.entity_id): CachedEmbedding(
                key=EmbeddingKey(row.entity_type, row.entity_id),
                model_id=row.embedding_model_id,
                template_version=row.text_template_version,
                text_hash=row.text_hash,
                dimension=row.embedding_dim,
                vector=[float(value) for value in row.embedding_vector],
            )
            for row in rows
        }

    async def upsert_embeddings(self, records: Iterable[CachedEmbedding]) -> None:
        from sqlalchemy import select

        from app.models.graph_node_embedding import GraphNodeEmbedding

        records = list(records)
        if not records:
            return
        async with self._new_session() as session:
            for record in records:
                row = (
                    await session.execute(
                        select(GraphNodeEmbedding).where(
                            GraphNodeEmbedding.entity_type == record.key.entity_type,
                            GraphNodeEmbedding.entity_id == record.key.entity_id,
                            GraphNodeEmbedding.embedding_model_id == record.model_id,
                            GraphNodeEmbedding.text_template_version == record.template_version,
                        )
                    )
                ).scalar_one_or_none()
                if row is None:
                    row = GraphNodeEmbedding(
                        entity_type=record.key.entity_type,
                        entity_id=record.key.entity_id,
                        embedding_model_id=record.model_id,
                        text_template_version=record.template_version,
                        text_hash=record.text_hash,
                        embedding_dim=record.dimension,
                        embedding_vector=record.vector,
                    )
                    session.add(row)
                else:
                    row.text_hash = record.text_hash
                    row.embedding_dim = record.dimension
                    row.embedding_vector = record.vector
            await session.commit()

    async def delete_embeddings(self, keys: Iterable[EmbeddingKey]) -> None:
        from sqlalchemy import delete, or_

        from app.models.graph_node_embedding import GraphNodeEmbedding

        conditions = [
            (GraphNodeEmbedding.entity_type == key.entity_type)
            & (GraphNodeEmbedding.entity_id == key.entity_id)
            for key in keys
        ]
        if not conditions:
            return
        async with self._new_session() as session:
            await session.execute(delete(GraphNodeEmbedding).where(or_(*conditions)))
            await session.commit()


class InMemoryGraphRepository:
    """Small async repository useful for unit tests and local experiments."""

    def __init__(self, rows: GraphRows, embeddings: Iterable[CachedEmbedding] = ()):
        self.rows = rows
        self.embeddings = {record.key: record for record in embeddings}
        self.upserted: list[CachedEmbedding] = []

    async def load_rows(self) -> GraphRows:
        return self.rows

    async def load_embeddings(
        self,
        keys: Iterable[EmbeddingKey],
        model_id: str,
        template_version: str,
    ) -> dict[EmbeddingKey, CachedEmbedding]:
        return {
            key: record
            for key in keys
            if (record := self.embeddings.get(key)) is not None
            and record.model_id == model_id
            and record.template_version == template_version
        }

    async def upsert_embeddings(self, records: Iterable[CachedEmbedding]) -> None:
        for record in records:
            self.embeddings[record.key] = record
            self.upserted.append(record)

    async def delete_embeddings(self, keys: Iterable[EmbeddingKey]) -> None:
        for key in keys:
            self.embeddings.pop(key, None)
