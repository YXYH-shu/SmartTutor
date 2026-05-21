"""add relation tables – concepts, skills, and junction tables

Revision ID: 0002_add_relation
Revises: 0001_initial
Create Date: 2026-04-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002_add_relation"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    """Check if a table already exists (SQLite compatible)."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=:t"
        ),
        {"t": table_name},
    )
    return result.fetchone() is not None


def _column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column already exists in a table (SQLite compatible)."""
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table_name})"))
    return any(row[1] == column_name for row in result.fetchall())


def upgrade() -> None:
    # ── New standalone tables ────────────────────────────────────────────
    if not _table_exists("concepts"):
        op.create_table(
            "concepts",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("concept_desc", sa.Text(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    if not _table_exists("skills"):
        op.create_table(
            "skills",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("skill_name", sa.String(256), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    # ── Junction tables (many-to-many) ──────────────────────────────────
    if not _table_exists("resource_knowledge"):
        op.create_table(
            "resource_knowledge",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "resource_id",
                sa.String(36),
                sa.ForeignKey("learning_resources.id"),
                nullable=False,
            ),
            sa.Column(
                "kp_id",
                sa.String(36),
                sa.ForeignKey("knowledge_points.id"),
                nullable=False,
            ),
            sa.UniqueConstraint("resource_id", "kp_id"),
        )

    if not _table_exists("knowledge_knowledge"):
        op.create_table(
            "knowledge_knowledge",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "source_kp_id",
                sa.String(36),
                sa.ForeignKey("knowledge_points.id"),
                nullable=False,
            ),
            sa.Column(
                "target_kp_id",
                sa.String(36),
                sa.ForeignKey("knowledge_points.id"),
                nullable=False,
            ),
        )

    if not _table_exists("concept_knowledge"):
        op.create_table(
            "concept_knowledge",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "concept_id",
                sa.String(36),
                sa.ForeignKey("concepts.id"),
                nullable=False,
            ),
            sa.Column(
                "kp_id",
                sa.String(36),
                sa.ForeignKey("knowledge_points.id"),
                nullable=False,
            ),
            sa.UniqueConstraint("concept_id", "kp_id"),
        )

    if not _table_exists("skill_knowledge"):
        op.create_table(
            "skill_knowledge",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "skill_id",
                sa.String(36),
                sa.ForeignKey("skills.id"),
                nullable=False,
            ),
            sa.Column(
                "kp_id",
                sa.String(36),
                sa.ForeignKey("knowledge_points.id"),
                nullable=False,
            ),
            sa.UniqueConstraint("skill_id", "kp_id"),
        )

    # ── Add new columns to existing tables ───────────────────────────────
    if not _column_exists("knowledge_points", "grade_level"):
        op.add_column(
            "knowledge_points",
            sa.Column("grade_level", sa.String(32), nullable=True),
        )
    if not _column_exists("knowledge_points", "cognitive_level"):
        op.add_column(
            "knowledge_points",
            sa.Column("cognitive_level", sa.String(32), nullable=True),
        )

    if not _column_exists("learning_resources", "full_score"):
        op.add_column(
            "learning_resources",
            sa.Column("full_score", sa.Float(), nullable=True),
        )

    if not _column_exists("learner_resource_interactions", "result_type"):
        op.add_column(
            "learner_resource_interactions",
            sa.Column("result_type", sa.String(32), nullable=True),
        )
    if not _column_exists("learner_resource_interactions", "result_detail"):
        op.add_column(
            "learner_resource_interactions",
            sa.Column("result_detail", sa.JSON(), nullable=True),
        )
    if not _column_exists("learner_resource_interactions", "is_correct"):
        op.add_column(
            "learner_resource_interactions",
            sa.Column("is_correct", sa.Boolean(), nullable=True),
        )
    if not _column_exists("learner_resource_interactions", "score"):
        op.add_column(
            "learner_resource_interactions",
            sa.Column("score", sa.Float(), nullable=True),
        )

    if not _column_exists("learner_knowledge_interactions", "algorithm_version"):
        op.add_column(
            "learner_knowledge_interactions",
            sa.Column("algorithm_version", sa.String(32), nullable=True),
        )

    if not _column_exists("user_profiles", "grade_level"):
        op.add_column(
            "user_profiles",
            sa.Column("grade_level", sa.String(32), nullable=True),
        )


def downgrade() -> None:
    # ── Remove added columns ─────────────────────────────────────────────
    if _column_exists("user_profiles", "grade_level"):
        op.drop_column("user_profiles", "grade_level")

    if _column_exists("learner_knowledge_interactions", "algorithm_version"):
        op.drop_column("learner_knowledge_interactions", "algorithm_version")

    for col in ("score", "is_correct", "result_detail", "result_type"):
        if _column_exists("learner_resource_interactions", col):
            op.drop_column("learner_resource_interactions", col)

    if _column_exists("learning_resources", "full_score"):
        op.drop_column("learning_resources", "full_score")

    for col in ("cognitive_level", "grade_level"):
        if _column_exists("knowledge_points", col):
            op.drop_column("knowledge_points", col)

    # ── Drop junction tables first (they reference standalone tables) ────
    for t in ("skill_knowledge", "concept_knowledge", "knowledge_knowledge", "resource_knowledge"):
        if _table_exists(t):
            op.drop_table(t)

    # ── Drop standalone tables ───────────────────────────────────────────
    for t in ("skills", "concepts"):
        if _table_exists(t):
            op.drop_table(t)
