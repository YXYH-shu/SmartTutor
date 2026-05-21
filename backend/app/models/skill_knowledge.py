"""技能-知识点关联表 – 技能与知识点的多对多关系。"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SkillKnowledge(Base):
    __tablename__ = "skill_knowledge"
    __table_args__ = (
        UniqueConstraint("skill_id", "kp_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("skills.id"), nullable=False, comment="技能ID"
    )
    kp_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_points.id"), nullable=False, comment="知识点ID"
    )
