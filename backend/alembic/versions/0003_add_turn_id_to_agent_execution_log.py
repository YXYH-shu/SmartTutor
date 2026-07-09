"""add turn_id column to agent_execution_logs

Revision ID: cb50f33d6276
Revises: 0002_add_relation
Create Date: 2026-07-07
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "cb50f33d6276"
down_revision: Union[str, None] = "0002_add_relation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column already exists (SQLite / MySQL compatible PRAGMA)."""
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


def _index_exists(index_name: str, table_name: str) -> bool:
    conn = op.get_bind()
    try:
        result = conn.execute(
            sa.text("SELECT 1 FROM sqlite_master WHERE type='index' AND name=:n"),
            {"n": index_name},
        )
        return result.fetchone() is not None
    except Exception:
        result = conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.statistics "
                "WHERE table_name = :t AND index_name = :n LIMIT 1"
            ),
            {"t": table_name, "n": index_name},
        )
        return result.fetchone() is not None


def upgrade() -> None:
    if not _column_exists("agent_execution_logs", "turn_id"):
        op.add_column(
            "agent_execution_logs",
            sa.Column("turn_id", sa.String(36), nullable=True),
        )
    if not _index_exists("ix_agent_execution_logs_turn_id", "agent_execution_logs"):
        op.create_index(
            "ix_agent_execution_logs_turn_id",
            "agent_execution_logs",
            ["turn_id"],
        )


def downgrade() -> None:
    if _index_exists("ix_agent_execution_logs_turn_id", "agent_execution_logs"):
        op.drop_index(
            "ix_agent_execution_logs_turn_id", table_name="agent_execution_logs"
        )
    if _column_exists("agent_execution_logs", "turn_id"):
        op.drop_column("agent_execution_logs", "turn_id")
