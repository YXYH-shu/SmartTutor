"""Add durable cache for frozen graph node embeddings.

Revision ID: 8c4e7f0a1b92
Revises: 5fefb2164829
Create Date: 2026-08-04
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8c4e7f0a1b92"
down_revision: Union[str, None] = "5fefb2164829"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table_name)


def upgrade() -> None:
    if _table_exists("graph_node_embeddings"):
        return
    op.create_table(
        "graph_node_embeddings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("embedding_model_id", sa.String(255), nullable=False),
        sa.Column("text_template_version", sa.String(64), nullable=False),
        sa.Column("text_hash", sa.String(64), nullable=False),
        sa.Column("embedding_dim", sa.Integer(), nullable=False),
        sa.Column("embedding_vector", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "entity_type",
            "entity_id",
            "embedding_model_id",
            "text_template_version",
            name="uq_graph_node_embedding_identity",
        ),
    )
    op.create_index("ix_graph_node_embeddings_entity_type", "graph_node_embeddings", ["entity_type"])
    op.create_index("ix_graph_node_embeddings_entity_id", "graph_node_embeddings", ["entity_id"])


def downgrade() -> None:
    if _table_exists("graph_node_embeddings"):
        op.drop_table("graph_node_embeddings")
