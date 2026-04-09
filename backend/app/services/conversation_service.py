"""Conversation service – business logic for conversation CRUD."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user_profile import UserProfile

logger = logging.getLogger(__name__)


async def create_conversation(
    db: AsyncSession,
    user_id: str,
    title: str = "新对话",
    workflow_type: str | None = None,
) -> Conversation:
    """Create a new conversation and auto-infer workflow_type if needed."""
    if workflow_type is None:
        # Auto-infer: if user has no profile or level → onboarding
        result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        if not profile or profile.current_level in ("", None):
            workflow_type = "onboarding"
        else:
            workflow_type = "adaptive_learning"

    conv = Conversation(
        id=str(uuid.uuid4()),
        user_id=user_id,
        title=title,
        workflow_type=workflow_type,
    )
    db.add(conv)
    await db.flush()
    return conv


async def list_conversations(
    db: AsyncSession,
    user_id: str,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    """Return paginated conversations with a last-message preview."""
    # Count
    count_q = select(func.count()).select_from(Conversation).where(
        Conversation.user_id == user_id
    )
    total = (await db.execute(count_q)).scalar() or 0

    # Fetch
    q = (
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(q)).scalars().all()

    items = []
    for conv in rows:
        # Latest message preview
        msg_q = (
            select(Message.content)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        last_msg = (await db.execute(msg_q)).scalar_one_or_none()

        items.append(
            {
                "id": conv.id,
                "user_id": conv.user_id,
                "title": conv.title,
                "workflow_type": conv.workflow_type,
                "created_at": conv.created_at,
                "updated_at": conv.updated_at,
                "last_message": (last_msg[:80] + "...") if last_msg and len(last_msg) > 80 else last_msg,
            }
        )
    return items, total


async def get_conversation_detail(
    db: AsyncSession,
    conversation_id: str,
    message_limit: int = 50,
    before_id: str | None = None,
) -> dict[str, Any] | None:
    """Return conversation detail with paginated messages."""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        return None

    # Messages
    msg_q = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(message_limit)
    )
    if before_id:
        sub = select(Message.created_at).where(Message.id == before_id)
        msg_q = msg_q.where(Message.created_at < (sub))
    messages = list(reversed((await db.execute(msg_q)).scalars().all()))

    return {
        "id": conv.id,
        "user_id": conv.user_id,
        "title": conv.title,
        "workflow_type": conv.workflow_type,
        "created_at": conv.created_at,
        "updated_at": conv.updated_at,
        "messages": [
            {
                "id": m.id,
                "conversation_id": m.conversation_id,
                "role": m.role,
                "content": m.content,
                "agent_type": m.agent_type,
                "emotion_state": m.emotion_state,
                "metadata": m.metadata_,
                "created_at": m.created_at,
            }
            for m in messages
        ],
    }


async def update_title(
    db: AsyncSession, conversation_id: str, title: str
) -> None:
    await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(title=title)
    )
    await db.flush()


async def soft_delete(db: AsyncSession, conversation_id: str) -> None:
    """Permanently delete a conversation and all its messages."""
    # Delete messages first (foreign key constraint)
    await db.execute(
        Message.__table__.delete().where(Message.conversation_id == conversation_id)
    )
    # Delete agent execution logs
    from app.models.agent_execution_log import AgentExecutionLog
    await db.execute(
        AgentExecutionLog.__table__.delete().where(AgentExecutionLog.conversation_id == conversation_id)
    )
    # Delete the conversation itself
    await db.execute(
        Conversation.__table__.delete().where(Conversation.id == conversation_id)
    )
    await db.flush()
