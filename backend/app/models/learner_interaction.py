"""学习者交互记录表 – 学习者与资源、知识点、其他学习者之间的交互。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LearnerResourceInteraction(Base):
    """学习者-学习资源交互表"""

    __tablename__ = "learner_resource_interactions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    learner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, comment="学习者ID"
    )
    resource_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("learning_resources.id"), nullable=False, comment="资源ID"
    )
    learn_time: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="学习时长（秒）"
    )
    learn_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="学习评分 0-100"
    )
    emotion_category: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="学习时情感类别"
    )
    is_rec: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, comment="是否为推荐资源"
    )
    feedback_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="反馈评分 0-5"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class LearnerKnowledgeInteraction(Base):
    """学习者-知识点交互表（认知诊断用）"""

    __tablename__ = "learner_knowledge_interactions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    learner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, comment="学习者ID"
    )
    knowledge_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_points.id"), nullable=False, comment="知识点ID"
    )
    learn_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="掌握度评分 0-1"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


class LearnerLearnerRelation(Base):
    """学习者-学习者交互表（学伴推荐用）"""

    __tablename__ = "learner_learner_relations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    learner_a_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, comment="学习者A ID"
    )
    learner_b_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, comment="学习者B ID"
    )
    grade_diff: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="年级差异度"
    )
    behavior_sim: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="行为相似度"
    )
    path_sim: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="学习路径相似度"
    )
    knowledge_sim: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="知识结构相似度"
    )
    emotion_sim: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="情感状态相似度"
    )
    embed_sim: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="嵌入向量相似度"
    )
    interactions_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="交互次数"
    )
    score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="综合匹配分"
    )
    is_rec: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, comment="是否推荐过"
    )
    feedback_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="反馈评分"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
