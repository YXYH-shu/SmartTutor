"""Async database engine, session factory, and init helper."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# ---------------------------------------------------------------------------
# Engine – auto-detects SQLite vs MySQL from the URL
# ---------------------------------------------------------------------------
_engine_kwargs: dict = {"echo": settings.database.echo}

# SQLite doesn't support pool_size / pool_recycle
if not settings.database.url.startswith("sqlite"):
    _engine_kwargs.update(pool_size=10, max_overflow=20, pool_recycle=3600)

engine = create_async_engine(settings.database.url, **_engine_kwargs)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
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
