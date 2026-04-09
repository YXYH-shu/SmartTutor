"""Checkpoint model – LangGraph state persistence."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Checkpoint(Base):
    __tablename__ = "checkpoints"
    __table_args__ = (
        sa.PrimaryKeyConstraint("thread_id", "checkpoint_ns", "checkpoint_id"),
        {"extend_existing": True},
    )

    thread_id: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    checkpoint_ns: Mapped[str] = mapped_column(sa.String(255), default="", nullable=False)
    checkpoint_id: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    parent_checkpoint_id: Mapped[str | None] = mapped_column(
        sa.String(255), nullable=True
    )
    type: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    checkpoint: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", sa.JSON, nullable=True
    )
