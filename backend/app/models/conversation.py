"""Conversation model."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        sa.Index("ix_conversations_user_id", "user_id"),
        {"extend_existing": True},
    )

    id: Mapped[str] = mapped_column(
        sa.String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(
        sa.String(255), default="新对话", nullable=True
    )
    workflow_type: Mapped[str | None] = mapped_column(
        sa.String(64), nullable=True
    )
    current_stage: Mapped[str | None] = mapped_column(
        sa.String(64), nullable=True
    )
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
    ended_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    # relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", lazy="selectin")
    execution_logs = relationship("AgentExecutionLog", back_populates="conversation", lazy="selectin")
