"""Message model."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RoleEnum(str, PyEnum):
    user = "user"
    assistant = "assistant"
    system = "system"


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        sa.Index("ix_messages_conversation_id", "conversation_id"),
        {"extend_existing": True},
    )

    id: Mapped[str] = mapped_column(
        sa.String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    conversation_id: Mapped[str] = mapped_column(
        sa.String(36),
        sa.ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        sa.String(16), nullable=False
    )
    content: Mapped[str] = mapped_column(sa.Text, nullable=False)
    agent_type: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    emotion_state: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", sa.JSON, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # relationships
    conversation = relationship("Conversation", back_populates="messages")
