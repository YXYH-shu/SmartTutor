"""知识点-知识点关联表 – 知识点之间的前置/后续关系。"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class KnowledgeKnowledge(Base):
    __tablename__ = "knowledge_knowledge"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    source_kp_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_points.id"), nullable=False, comment="前置知识点"
    )
    target_kp_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_points.id"), nullable=False, comment="后续知识点"
    )
