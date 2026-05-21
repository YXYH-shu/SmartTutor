"""概念-知识点关联表 – 概念与知识点的多对多关系。"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ConceptKnowledge(Base):
    __tablename__ = "concept_knowledge"
    __table_args__ = (
        UniqueConstraint("concept_id", "kp_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    concept_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("concepts.id"), nullable=False, comment="概念ID"
    )
    kp_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_points.id"), nullable=False, comment="知识点ID"
    )
