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
        "turn_id": result.get("turn_id"),
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

    # Run graph with step progress streaming
    engine = _get_engine()
    step_queue: asyncio.Queue = asyncio.Queue()
    thinking_steps_buffer: list[dict] = []

    async def _run_engine() -> dict[str, Any]:
        try:
            result = await engine.process_turn(
                user_id=user_id,
                conversation_id=conversation_id,
                user_message=content,
                step_queue=step_queue,
                thinking_steps=thinking_steps_buffer,
            )
            await step_queue.put({"type": "result", "data": result})
        except Exception as exc:
            logger.exception("Graph execution failed")
            await step_queue.put({"type": "error", "error": str(exc)})

    engine_task = asyncio.create_task(_run_engine())

    # Yield step events while graph is running
    result: dict[str, Any] = {}
    while True:
        item = await step_queue.get()
        if item["type"] == "step":
            step_data = json.dumps(
                {"type": "step", "label": item["label"], "step": item.get("step", "")}, ensure_ascii=False
            )
            yield f"data: {step_data}\n\n"
            # Accumulate into buffer for persistence
            thinking_steps_buffer.append({
                "step": item.get("step", ""),
                "label": item.get("label", ""),
                "content": "",
                "status": "running",
            })
        elif item["type"] == "thinking":
            thinking_data = json.dumps(
                {"type": "thinking", "content": item.get("content", ""), "step": item.get("step", ""), "label": item.get("label", "")},
                ensure_ascii=False,
            )
            yield f"data: {thinking_data}\n\n"
            # Update the matching running step entry with content & completed status
            for entry in reversed(thinking_steps_buffer):
                if (
                    entry.get("status") == "running"
                    and entry.get("step", "") == item.get("step", "")
                ):
                    entry["content"] = item.get("content", "")
                    entry["status"] = "completed"
                    if item.get("label"):
                        entry["label"] = item["label"]
                    break
        elif item["type"] == "result":
            result = item["data"]
            break
        elif item["type"] == "error":
            err_data = json.dumps(
                {"type": "error", "detail": item["error"]}, ensure_ascii=False
            )
            yield f"data: {err_data}\n\n"
            engine_task.cancel()
            return

    # Stream content chunks
    response_text = result.get("response", "")
    chunks = _split_response(response_text)
    for chunk in chunks:
        data = json.dumps({"type": "content", "content": chunk}, ensure_ascii=False)
        yield f"data: {data}\n\n"
        await asyncio.sleep(0.02)

    # Send metadata
    kt_summary = result.get("kt_summary") or {}
    kt_summary_clean = {
        "knowledgeStates": kt_summary.get("knowledgeStates", []) if isinstance(kt_summary, dict) else [],
        "weakPoints": kt_summary.get("weakPoints", []) if isinstance(kt_summary, dict) else [],
        "diagnosisSource": kt_summary.get("diagnosisSource", "llm_simulation") if isinstance(kt_summary, dict) else "llm_simulation",
        "modelInfo": kt_summary.get("modelInfo", {}) if isinstance(kt_summary, dict) else {},
        "metrics": kt_summary.get("metrics", {}) if isinstance(kt_summary, dict) else {},
    }
    if isinstance(kt_summary, dict) and kt_summary.get("diagnosisSummary"):
        kt_summary_clean["diagnosisSummary"] = kt_summary["diagnosisSummary"]
    meta = json.dumps(
        {
            "type": "done",
            "workflow": result.get("workflow"),
            "stage": result.get("stage"),
            "turn_id": result.get("turn_id"),
            # 轮次级聚合数据（focus / KT），与前端 StreamDonePayload 对齐
            "turnId": result.get("turn_id"),
            "focusAgents": result.get("focus_agents") or [],
            "touchedNodes": result.get("touched_knowledge_nodes") or [],
            "trajectory": result.get("trajectory") or [],
            "ktSummary": kt_summary_clean,
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
        "thinking_steps": m.thinking_steps,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _split_response(text: str) -> list[str]:
    """Split text into streaming chunks (sentence-level)."""
    if not text:
        return [""]
    # Split on sentence-ending punctuation, keeping the punctuation
    parts = re.split(r"(?<=[。！？\n])", text)
    return [p for p in parts if p]
