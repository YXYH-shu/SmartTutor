"""AgentExecutionLog model – records each agent invocation."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AgentExecutionLog(Base):
    __tablename__ = "agent_execution_logs"
    __table_args__ = (
        sa.Index("ix_agent_logs_conversation_id", "conversation_id"),
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
    agent_name: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    input_payload: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    output_payload: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    execution_time_ms: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    turn_id: Mapped[str | None] = mapped_column(
        sa.String(36), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # relationships
    conversation = relationship("Conversation", back_populates="execution_logs")
