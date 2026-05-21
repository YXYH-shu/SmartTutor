"""资源-知识点关联表 – 学习资源与知识点的多对多关系。"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ResourceKnowledge(Base):
    __tablename__ = "resource_knowledge"
    __table_args__ = (
        UniqueConstraint("resource_id", "kp_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("learning_resources.id"), nullable=False, comment="资源ID"
    )
    kp_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_points.id"), nullable=False, comment="知识点ID"
    )
