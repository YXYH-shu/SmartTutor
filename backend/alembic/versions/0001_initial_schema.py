"""initial schema – all tables

Revision ID: 0001_initial
Revises: None
Create Date: 2026-04-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Core user / conversation tables ──────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
    )

    op.create_table(
        "user_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
            index=True,
        ),
        sa.Column("knowledge_graph", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("learning_style", sa.String(32), nullable=True),
        sa.Column(
            "current_level", sa.String(32), nullable=False, server_default="'初级'"
        ),
        sa.Column("weak_points", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("preferences", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("last_diagnosis", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("title", sa.String(255), server_default="'新对话'"),
        sa.Column("workflow_type", sa.String(64), nullable=True),
        sa.Column("current_stage", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("agent_type", sa.String(64), nullable=True),
        sa.Column("emotion_state", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "message_feedbacks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "message_id",
            sa.String(36),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("feedback_type", sa.String(32), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "agent_execution_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=True),
        sa.Column("output_payload", sa.JSON(), nullable=True),
        sa.Column("execution_time_ms", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "checkpoints",
        sa.Column("thread_id", sa.String(255), primary_key=True),
        sa.Column("checkpoint_ns", sa.String(255), primary_key=True, server_default=""),
        sa.Column("checkpoint_id", sa.String(255), primary_key=True),
        sa.Column("parent_checkpoint_id", sa.String(255), nullable=True),
        sa.Column("type", sa.String(128), nullable=True),
        sa.Column("checkpoint", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
    )

    # ── Knowledge graph tables ───────────────────────────────────────
    op.create_table(
        "knowledge_points",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("subject", sa.String(64), nullable=True),
        sa.Column("grade", sa.String(32), nullable=True),
        sa.Column("pre_knowledge", sa.JSON(), nullable=True),
        sa.Column(
            "parent_knowledge",
            sa.String(36),
            sa.ForeignKey("knowledge_points.id"),
            nullable=True,
        ),
        sa.Column("standard", sa.String(128), nullable=True),
        sa.Column("difficult", sa.Float(), nullable=True),
        sa.Column("embed", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ── Learning resources ───────────────────────────────────────────
    op.create_table(
        "learning_resources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("type", sa.String(32), nullable=True),
        sa.Column("url", sa.String(1024), nullable=True),
        sa.Column("difficult", sa.Float(), nullable=True),
        sa.Column("time_need", sa.Integer(), nullable=True),
        sa.Column("knowledge_coverage", sa.JSON(), nullable=True),
        sa.Column("embed", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ── Learner interactions ─────────────────────────────────────────
    op.create_table(
        "learner_resource_interactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "learner_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "resource_id",
            sa.String(36),
            sa.ForeignKey("learning_resources.id"),
            nullable=False,
        ),
        sa.Column("learn_time", sa.Integer(), nullable=True),
        sa.Column("learn_score", sa.Float(), nullable=True),
        sa.Column("emotion_category", sa.String(32), nullable=True),
        sa.Column("is_rec", sa.Boolean(), nullable=True),
        sa.Column("feedback_score", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "learner_knowledge_interactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "learner_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "knowledge_id",
            sa.String(36),
            sa.ForeignKey("knowledge_points.id"),
            nullable=False,
        ),
        sa.Column("learn_score", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "learner_learner_relations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "learner_a_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "learner_b_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("grade_diff", sa.Float(), nullable=True),
        sa.Column("behavior_sim", sa.Float(), nullable=True),
        sa.Column("path_sim", sa.Float(), nullable=True),
        sa.Column("knowledge_sim", sa.Float(), nullable=True),
        sa.Column("emotion_sim", sa.Float(), nullable=True),
        sa.Column("embed_sim", sa.Float(), nullable=True),
        sa.Column("interactions_count", sa.Integer(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("is_rec", sa.Boolean(), nullable=True),
        sa.Column("feedback_score", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ── Recommendation records ───────────────────────────────────────
    op.create_table(
        "resource_recommendations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("conversations.id"),
            nullable=True,
        ),
        sa.Column(
            "learner_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("candidates", sa.JSON(), nullable=True),
        sa.Column("rec_num", sa.Integer(), nullable=True),
        sa.Column("labels", sa.JSON(), nullable=True),
        sa.Column("kg_version", sa.String(64), nullable=True),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column("rec_resources", sa.JSON(), nullable=True),
        sa.Column("rec_ranks", sa.JSON(), nullable=True),
        sa.Column("feedback_score", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "buddy_recommendations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("conversations.id"),
            nullable=True,
        ),
        sa.Column(
            "learner_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("candidates", sa.JSON(), nullable=True),
        sa.Column("rec_num", sa.Integer(), nullable=True),
        sa.Column("train_labels", sa.JSON(), nullable=True),
        sa.Column("kg_version", sa.String(64), nullable=True),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column("rec_strategy", sa.String(64), nullable=True),
        sa.Column("rec_partners", sa.JSON(), nullable=True),
        sa.Column("rec_ranks", sa.JSON(), nullable=True),
        sa.Column("rec_feedback", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("buddy_recommendations")
    op.drop_table("resource_recommendations")
    op.drop_table("learner_learner_relations")
    op.drop_table("learner_knowledge_interactions")
    op.drop_table("learner_resource_interactions")
    op.drop_table("learning_resources")
    op.drop_table("knowledge_points")
    op.drop_table("agent_execution_logs")
    op.drop_table("message_feedbacks")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("user_profiles")
    op.drop_table("checkpoints")
    op.drop_table("users")
