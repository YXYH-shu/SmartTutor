"""SessionFeedback model – stores end-of-session questionnaire answers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SessionFeedback(Base):
    __tablename__ = "session_feedbacks"
    __table_args__ = (
        sa.UniqueConstraint("conversation_id", name="uq_session_feedbacks_conversation_id"),
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
    user_id: Mapped[str] = mapped_column(
        sa.String(36),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    q1_score: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    q2_score: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    q3_score: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    total_score: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
