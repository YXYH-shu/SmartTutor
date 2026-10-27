"""Add session_feedbacks table and conversations.ended_at.

Revision ID: 0006_session_feedback
Revises: 8c4e7f0a1b92
Create Date: 2026-10-27
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0006_session_feedback"
down_revision: Union[str, None] = "8c4e7f0a1b92"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column already exists (SQLite / MySQL compatible)."""
    conn = op.get_bind()
    try:
        result = conn.execute(sa.text(f"PRAGMA table_info({table_name})"))
        return any(row[1] == column_name for row in result.fetchall())
    except Exception:
        # MySQL – fall back to information_schema
        result = conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c LIMIT 1"
            ),
            {"t": table_name, "c": column_name},
        )
        return result.fetchone() is not None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table_name)


def upgrade() -> None:
    if not _column_exists("conversations", "ended_at"):
        op.add_column(
            "conversations",
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        )

    if not _table_exists("session_feedbacks"):
        op.create_table(
            "session_feedbacks",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("conversation_id", sa.String(36), nullable=False),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("q1_score", sa.Integer(), nullable=False),
            sa.Column("q2_score", sa.Integer(), nullable=False),
            sa.Column("q3_score", sa.Integer(), nullable=False),
            sa.Column("total_score", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("conversation_id", name="uq_session_feedbacks_conversation_id"),
        )


def downgrade() -> None:
    if _table_exists("session_feedbacks"):
        op.drop_table("session_feedbacks")

    if _column_exists("conversations", "ended_at"):
        op.drop_column("conversations", "ended_at")
