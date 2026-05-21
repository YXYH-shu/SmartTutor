"""知识点表 – 存储学科知识图谱中的节点。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class KnowledgePoint(Base):
    __tablename__ = "knowledge_points"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="知识点名称")
    content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="知识点内容描述")
    subject: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="所属学科")
    grade: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="适用年级")
    pre_knowledge: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="前置知识点ID列表"
    )
    parent_knowledge: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("knowledge_points.id"), nullable=True, comment="父知识点"
    )
    standard: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="课程标准"
    )
    difficult: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="难度系数 0-1"
    )
    embed: Mapped[str | None] = mapped_column(Text, nullable=True, comment="向量嵌入（JSON）")
    grade_level: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="适用学段/年级"
    )
    cognitive_level: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="认知层次（布鲁姆分类）"
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

    # relationships
    children: Mapped[list["KnowledgePoint"]] = relationship()
