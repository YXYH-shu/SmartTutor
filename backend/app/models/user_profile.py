"""UserProfile model – stores per-student learning metadata."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"
    __table_args__ = (
        sa.Index("ix_user_profiles_user_id", "user_id", unique=True),
        {"extend_existing": True},
    )

    id: Mapped[str] = mapped_column(
        sa.String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        sa.String(36),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    knowledge_graph: Mapped[dict] = mapped_column(
        sa.JSON, default=dict, nullable=False
    )
    learning_style: Mapped[str | None] = mapped_column(
        sa.String(32), nullable=True
    )
    current_level: Mapped[str] = mapped_column(
        sa.String(32), default="初级", nullable=False
    )
    weak_points: Mapped[dict] = mapped_column(
        sa.JSON, default=list, nullable=False
    )
    preferences: Mapped[dict] = mapped_column(
        sa.JSON, default=dict, nullable=False
    )
    last_diagnosis: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    grade_level: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # relationships
    user = relationship("User", back_populates="profile")
