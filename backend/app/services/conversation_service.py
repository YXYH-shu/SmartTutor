"""Conversation service – business logic for conversation CRUD."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.agent_execution_log import AgentExecutionLog
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.session_feedback import SessionFeedback
from app.models.user_profile import UserProfile

logger = logging.getLogger(__name__)


async def end_conversation(db: AsyncSession, conversation: Conversation) -> Conversation:
    """Mark a conversation as ended (idempotent)."""
    if conversation.ended_at is None:
        conversation.ended_at = datetime.now(timezone.utc)
        await db.flush()
    return conversation


async def submit_session_questionnaire(
    db: AsyncSession,
    conversation: Conversation,
    q1: int,
    q2: int,
    q3: int,
) -> SessionFeedback:
    """Persist a 3-question Likert questionnaire and end the conversation."""
    feedback = SessionFeedback(
        id=str(uuid.uuid4()),
        conversation_id=conversation.id,
        user_id=conversation.user_id,
        q1_score=q1,
        q2_score=q2,
        q3_score=q3,
        total_score=q1 + q2 + q3,
    )
    db.add(feedback)
    conversation.ended_at = datetime.now(timezone.utc)
    await db.flush()
    return feedback


async def count_user_messages(db: AsyncSession, conversation_id: str) -> int:
    """Count user-role messages in a conversation."""
    result = await db.execute(
        select(func.count())
        .select_from(Message)
        .where(Message.conversation_id == conversation_id, Message.role == "user")
    )
    return result.scalar() or 0


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
    """Return paginated conversations with last-message preview + agent hints.

    Aggregation strategy (avoids N+1):
    1. One query to fetch the page of conversations.
    2. One query to fetch the latest message per conversation in the page
       (correlated subquery).
    3. One query to fetch the latest AgentExecutionLog per conversation in
       the page – used to derive highlight_agent + knowledge_points.

    Result: 3 SQL round trips, regardless of page_size.
    """
    # Count
    count_q = select(func.count()).select_from(Conversation).where(
        Conversation.user_id == user_id
    )
    total = (await db.execute(count_q)).scalar() or 0

    # Fetch the page
    q = (
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(q)).scalars().all()

    if not rows:
        return [], total

    conv_ids = [c.id for c in rows]

    # ── Latest message per conversation (batch) ──────────────────────
    # Use a correlated subquery on max(created_at).
    latest_msg_sub = (
        select(
            Message.conversation_id.label("cid"),
            Message.content.label("content"),
            Message.created_at.label("created_at"),
            func.row_number()
            .over(
                partition_by=Message.conversation_id,
                order_by=Message.created_at.desc(),
            )
            .label("rn"),
        )
        .where(Message.conversation_id.in_(conv_ids))
    ).subquery()

    msg_rows = (
        await db.execute(
            select(latest_msg_sub.c.cid, latest_msg_sub.c.content).where(
                latest_msg_sub.c.rn == 1
            )
        )
    ).all()
    msg_by_cid = {row.cid: row.content for row in msg_rows}

    # ── Latest AgentExecutionLog per conversation (batch) ────────────
    log_sub = (
        select(
            AgentExecutionLog.conversation_id.label("cid"),
            AgentExecutionLog.agent_name.label("agent_name"),
            AgentExecutionLog.output_payload.label("output_payload"),
            AgentExecutionLog.created_at.label("created_at"),
            func.row_number()
            .over(
                partition_by=AgentExecutionLog.conversation_id,
                order_by=AgentExecutionLog.created_at.desc(),
            )
            .label("rn"),
        )
        .where(AgentExecutionLog.conversation_id.in_(conv_ids))
    ).subquery()

    log_rows = (
        await db.execute(
            select(
                log_sub.c.cid,
                log_sub.c.agent_name,
                log_sub.c.output_payload,
            ).where(log_sub.c.rn == 1)
        )
    ).all()
    log_by_cid = {row.cid: row for row in log_rows}

    items: list[dict[str, Any]] = []
    for conv in rows:
        last_msg = msg_by_cid.get(conv.id)
        last_log = log_by_cid.get(conv.id)
        highlight_agent = last_log.agent_name if last_log else None
        knowledge_points = (
            _extract_knowledge_points(last_log.output_payload) if last_log else None
        )
        items.append(
            {
                "id": conv.id,
                "user_id": conv.user_id,
                "title": conv.title,
                "workflow_type": conv.workflow_type,
                "created_at": conv.created_at,
                "updated_at": conv.updated_at,
                "ended_at": conv.ended_at,
                "last_message": (
                    last_msg[:80] + "..." if last_msg and len(last_msg) > 80 else last_msg
                ),
                "knowledge_points": knowledge_points,
                "highlight_agent": highlight_agent,
            }
        )
    return items, total


def _extract_knowledge_points(payload: Any, limit: int = 6) -> list[dict[str, Any]]:
    """Best-effort skill/knowledge node extraction from an agent output payload.

    Looks at common shapes:
    - {"mastery_rates": {"skill_id": 0.x, ...}}
    - {"weak_points": [...]}
    - {"knowledge_graph": {...}}
    - {"target_knowledge": [...]}
    Returns up to ``limit`` nodes with mastery when available.
    """
    if not isinstance(payload, dict):
        return []

    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()

    mastery_map = payload.get("mastery_rates")
    if isinstance(mastery_map, dict):
        for sid, score in mastery_map.items():
            if not sid or sid in seen:
                continue
            seen.add(sid)
            nodes.append(
                {
                    "id": str(sid),
                    "label": str(sid),
                    "mastery": float(score) if isinstance(score, (int, float)) else None,
                    "status": (
                        "mastered"
                        if isinstance(score, (int, float)) and score >= 0.8
                        else (
                            "learning"
                            if isinstance(score, (int, float)) and score >= 0.5
                            else "weak"
                        )
                    ),
                }
            )
            if len(nodes) >= limit:
                return nodes

    kg = payload.get("knowledge_graph")
    if isinstance(kg, dict):
        for sid, score in kg.items():
            if not sid or sid in seen:
                continue
            seen.add(sid)
            nodes.append(
                {
                    "id": str(sid),
                    "label": str(sid),
                    "mastery": float(score) if isinstance(score, (int, float)) else None,
                    "status": (
                        "mastered"
                        if isinstance(score, (int, float)) and score >= 0.8
                        else (
                            "learning"
                            if isinstance(score, (int, float)) and score >= 0.5
                            else "weak"
                        )
                    ),
                }
            )
            if len(nodes) >= limit:
                return nodes

    weak = payload.get("weak_points")
    if isinstance(weak, list):
        for wp in weak:
            text = wp if isinstance(wp, str) else (
                wp.get("skill_id") or wp.get("name") or wp.get("label")
                if isinstance(wp, dict) else None
            )
            if not text or text in seen:
                continue
            seen.add(text)
            nodes.append(
                {"id": text, "label": text, "mastery": None, "status": "weak"}
            )
            if len(nodes) >= limit:
                return nodes

    target = payload.get("target_knowledge")
    if isinstance(target, list):
        for tk in target:
            text = tk if isinstance(tk, str) else (
                tk.get("skill_id") or tk.get("name")
                if isinstance(tk, dict) else None
            )
            if not text or text in seen:
                continue
            seen.add(text)
            nodes.append(
                {"id": text, "label": text, "mastery": None, "status": "learning"}
            )
            if len(nodes) >= limit:
                return nodes

    return nodes


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
        "ended_at": conv.ended_at,
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
