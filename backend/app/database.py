"""Async database engine, session factory, and init helper."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session

from app.config import settings

logger = logging.getLogger(__name__)
_GRAPH_CHANGES_KEY = "graph_recommender_changes"


def _graph_change_for(instance: object, operation: str) -> Any | None:
    """Translate a committed graph-source ORM mutation into a graph refresh hint."""
    from algorithm.graph_recommender.data.types import GraphChange
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

    if isinstance(instance, User):
        return GraphChange(operation, "learner", entity_id=str(instance.id))
    if isinstance(instance, UserProfile):
        return GraphChange(operation, "learner", entity_id=str(instance.user_id))
    if isinstance(instance, LearningResource):
        return GraphChange(operation, "resource", entity_id=str(instance.id))
    if isinstance(instance, KnowledgePoint):
        return GraphChange(operation, "knowledge_point", entity_id=str(instance.id))
    if isinstance(instance, LearnerResourceInteraction):
        return GraphChange(
            operation,
            "edge",
            relation_type="interacted_with",
            source_id=str(instance.learner_id),
            target_id=str(instance.resource_id),
        )
    if isinstance(instance, ResourceKnowledge):
        return GraphChange(
            operation,
            "edge",
            relation_type="covers",
            source_id=str(instance.resource_id),
            target_id=str(instance.kp_id),
        )
    if isinstance(instance, LearnerKnowledgeInteraction):
        return GraphChange(
            operation,
            "edge",
            relation_type="has_knowledge_state",
            source_id=str(instance.learner_id),
            target_id=str(instance.knowledge_id),
        )
    if isinstance(instance, KnowledgeKnowledge):
        return GraphChange(
            operation,
            "edge",
            relation_type="precedes",
            source_id=str(instance.source_kp_id),
            target_id=str(instance.target_kp_id),
        )
    if isinstance(instance, LearnerLearnerRelation):
        return GraphChange(
            operation,
            "edge",
            relation_type="partnered_with",
            source_id=str(instance.learner_a_id),
            target_id=str(instance.learner_b_id),
        )
    return None


@event.listens_for(Session, "after_flush")
def _collect_graph_changes(session: Session, _flush_context: object) -> None:
    changes = session.info.setdefault(_GRAPH_CHANGES_KEY, [])
    for operation, instances in (
        ("upsert", (*session.new, *session.dirty)),
        ("delete", tuple(session.deleted)),
    ):
        for instance in instances:
            if operation == "upsert" and instance not in session.new and not session.is_modified(
                instance, include_collections=False
            ):
                continue
            change = _graph_change_for(instance, operation)
            if change is not None:
                changes.append(change)


@event.listens_for(Session, "after_rollback")
def _discard_graph_changes(session: Session) -> None:
    session.info.pop(_GRAPH_CHANGES_KEY, None)


async def _sync_graph_changes(changes: list[Any]) -> None:
    """Refresh the graph structure after a successful application transaction."""
    if not changes:
        return
    unique_changes = list(dict.fromkeys(changes))
    await _run_graph_sync(unique_changes)


async def _run_graph_sync(changes: list[Any]) -> None:
    try:
        from algorithm.graph_recommender import get_graph_recommender

        await get_graph_recommender().sync_after_commit(changes)
    except RuntimeError:
        # The service may commit seed data before the graph recommender starts.
        return
    except Exception:
        logger.exception("Graph recommender refresh failed after database commit")


class GraphAwareAsyncSession(AsyncSession):
    """Async session that publishes graph structure changes before commit returns."""

    async def commit(self) -> None:
        await super().commit()
        changes = self.sync_session.info.pop(_GRAPH_CHANGES_KEY, [])
        await _sync_graph_changes(changes)


def _resolve_database_url(value: str) -> str:
    """Keep relative SQLite databases anchored to backend/, not the process cwd."""
    url = make_url(value)
    if not url.drivername.startswith("sqlite") or not url.database or url.database == ":memory:":
        return value
    database_path = Path(url.database)
    if database_path.is_absolute():
        return value
    backend_dir = Path(__file__).resolve().parents[1]
    return str(url.set(database=(backend_dir / database_path).resolve().as_posix()))


database_url = _resolve_database_url(settings.database.url)

# ---------------------------------------------------------------------------
# Engine – auto-detects SQLite vs MySQL from the URL
# ---------------------------------------------------------------------------
_engine_kwargs: dict = {"echo": settings.database.echo}

# SQLite doesn't support pool_size / pool_recycle
if not database_url.startswith("sqlite"):
    _engine_kwargs.update(pool_size=10, max_overflow=20, pool_recycle=3600)

engine = create_async_engine(database_url, **_engine_kwargs)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=GraphAwareAsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Base class for all ORM models
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """Declarative base – import this in every model module."""

    pass


# ---------------------------------------------------------------------------
# Init helper (used by docker-compose entrypoint or CLI)
# ---------------------------------------------------------------------------


async def init_db() -> None:
    """Create all tables that do not yet exist.

    In production you should rely on Alembic migrations instead.
    This helper is convenient for local development and CI.
    """
    # Import all models so they register on Base.metadata
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
