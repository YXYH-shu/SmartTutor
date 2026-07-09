"""add thinking_steps to message

Revision ID: 5fefb2164829
Revises: cb50f33d6276
Create Date: 2026-07-08
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5fefb2164829"
down_revision: Union[str, None] = "cb50f33d6276"
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


def upgrade() -> None:
    if not _column_exists("messages", "thinking_steps"):
        op.add_column(
            "messages",
            sa.Column("thinking_steps", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    if _column_exists("messages", "thinking_steps"):
        op.drop_column("messages", "thinking_steps")
