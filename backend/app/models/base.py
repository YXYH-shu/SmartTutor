"""Common mixin for all models – provides id, created_at, updated_at."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.database import Base


def _new_uuid() -> str:
    """Generate a UUID7-like string (uses uuid4 for simplicity)."""
    return str(uuid.uuid4())


class TimestampMixin:
    """Provides ``created_at`` and ``updated_at`` columns."""

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
