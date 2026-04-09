"""Chat service – orchestrates message sending and AI interaction."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.models.message_feedback import MessageFeedback

logger = logging.getLogger(__name__)

# Lazy singleton for the graph engine
_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        from app.graph.engine import TutorGraphEngine
        _engine = TutorGraphEngine()
    return _engine


async def send_message(
    db: AsyncSession,
    user_id: str,
    conversation_id: str,
    content: str,
) -> dict[str, Any]:
    """Non-streaming: save user msg → run graph → return AI response."""
    # Save user message
    user_msg = Message(
        id=str(uuid.uuid4()),
        conversation_id=conversation_id,
        role="user",
        content=content,
    )
    db.add(user_msg)
    await db.flush()

    # Run graph engine
    engine = _get_engine()
    result = await engine.process_turn(
        user_id=user_id,
        conversation_id=conversation_id,
        user_message=content,
    )

    # The engine already saved both messages, but we need the assistant msg object
    assistant_msg_q = (
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.role == "assistant",
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    assistant_msg = (await db.execute(assistant_msg_q)).scalar_one_or_none()

    return {
        "message": _msg_to_dict(assistant_msg) if assistant_msg else {"content": result["response"]},
        "workflow": result.get("workflow"),
        "stage": result.get("stage"),
    }


async def stream_message(
    user_id: str,
    conversation_id: str,
    content: str,
) -> AsyncGenerator[str, None]:
    """SSE streaming: save user msg → run graph → yield chunks.

    The graph itself is not yet streaming internally, so we simulate
    token-level streaming by splitting the final response.
    """
    # Save user message (need separate session since we yield control)
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        user_msg = Message(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            role="user",
            content=content,
        )
        db.add(user_msg)
        await db.commit()

    # Run graph
    engine = _get_engine()
    result = await engine.process_turn(
        user_id=user_id,
        conversation_id=conversation_id,
        user_message=content,
    )
    response_text = result.get("response", "")

    # Split into sentence-level chunks for streaming effect
    chunks = _split_response(response_text)
    for chunk in chunks:
        data = json.dumps({"type": "content", "content": chunk}, ensure_ascii=False)
        yield f"data: {data}\n\n"
        await asyncio.sleep(0.02)

    # Send metadata
    meta = json.dumps(
        {
            "type": "done",
            "workflow": result.get("workflow"),
            "stage": result.get("stage"),
        },
        ensure_ascii=False,
    )
    yield f"data: {meta}\n\n"


async def save_feedback(
    db: AsyncSession,
    message_id: str,
    feedback_type: str,
    comment: str | None,
) -> MessageFeedback:
    fb = MessageFeedback(
        id=str(uuid.uuid4()),
        message_id=message_id,
        feedback_type=feedback_type,
        comment=comment,
    )
    db.add(fb)
    await db.flush()
    return fb


async def get_history(
    db: AsyncSession,
    conversation_id: str,
    before_id: str | None = None,
    limit: int = 20,
) -> list[dict]:
    q = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    if before_id:
        sub = select(Message.created_at).where(Message.id == before_id)
        q = q.where(Message.created_at < sub)
    messages = list(reversed((await db.execute(q)).scalars().all()))
    return [_msg_to_dict(m) for m in messages]


# ── Helpers ──────────────────────────────────────────────────────────


def _msg_to_dict(m: Message) -> dict:
    return {
        "id": m.id,
        "conversation_id": m.conversation_id,
        "role": m.role,
        "content": m.content,
        "agent_type": m.agent_type,
        "emotion_state": m.emotion_state,
        "metadata": m.metadata_,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _split_response(text: str) -> list[str]:
    """Split text into streaming chunks (sentence-level)."""
    if not text:
        return [""]
    # Split on sentence-ending punctuation, keeping the punctuation
    parts = re.split(r"(?<=[。！？\n])", text)
    return [p for p in parts if p]
