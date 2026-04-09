"""学习资源表 – 存储课程视频、文章、测验等学习材料。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LearningResource(Base):
    __tablename__ = "learning_resources"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="资源名称")
    content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="资源内容描述")
    type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="资源类型：video/article/quiz/practice"
    )
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True, comment="资源链接")
    difficult: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="难度系数 0-1"
    )
    time_need: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="预计学习时长（分钟）"
    )
    knowledge_coverage: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="覆盖知识点ID及权重"
    )
    embed: Mapped[str | None] = mapped_column(Text, nullable=True, comment="向量嵌入（JSON）")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
