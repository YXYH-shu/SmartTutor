"""推荐记录表 – 资源推荐和学伴推荐的记录。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ResourceRecommendation(Base):
    """资源推荐记录表"""

    __tablename__ = "resource_recommendations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("conversations.id"), nullable=True, comment="会话ID"
    )
    learner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, comment="学习者ID"
    )
    candidates: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="候选资源ID及召回来源"
    )
    rec_num: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="推荐数量"
    )
    labels: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="标签/特征信息"
    )
    kg_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="知识图谱版本"
    )
    model_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="推荐模型版本"
    )
    rec_resources: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="推荐的资源列表（含ID、类型、标题等）"
    )
    rec_ranks: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="推荐排序结果"
    )
    feedback_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="用户反馈评分"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class BuddyRecommendation(Base):
    """学伴推荐记录表"""

    __tablename__ = "buddy_recommendations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("conversations.id"), nullable=True, comment="会话ID"
    )
    learner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, comment="学习者ID"
    )
    candidates: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="候选学伴ID及匹配分"
    )
    rec_num: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="推荐数量"
    )
    train_labels: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="训练标签"
    )
    kg_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="知识图谱版本"
    )
    model_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="匹配模型版本"
    )
    rec_strategy: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="推荐策略"
    )
    rec_partners: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="推荐的学伴列表"
    )
    rec_ranks: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="推荐排序结果"
    )
    rec_feedback: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="推荐反馈评分"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
