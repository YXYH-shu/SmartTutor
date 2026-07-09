"""Chat routes – send messages, stream responses, feedback, history."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DBSession, CurrentUser, get_conversation
from app.api.schemas import (
    AgentTurnLogResponse,
    ChatResponse,
    HistoryQueryParams,
    MessageFeedbackRequest,
    MessageFeedbackResponse,
    MessageResponse,
    PaginatedResponse,
    RegenerateRequest,
    SendMessageRequest,
)
from app.models.agent_execution_log import AgentExecutionLog
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.message_feedback import MessageFeedback
from app.services import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/send", response_model=ChatResponse)
async def send_message(body: SendMessageRequest, user: CurrentUser, db: DBSession):
    """Send a message and get a non-streaming AI response."""
    # Verify conversation ownership
    await get_conversation(body.conversation_id, user, db)

    result = await chat_service.send_message(
        db, user.id, body.conversation_id, body.content
    )
    return ChatResponse(
        message=result["message"],
        workflow=result.get("workflow"),
        stage=result.get("stage"),
        turn_id=result.get("turn_id"),
    )


@router.post("/stream")
async def stream_message(body: SendMessageRequest, user: CurrentUser, db: DBSession):
    """Send a message and receive an SSE streaming response.

    The response uses ``text/event-stream`` content type. Each data frame
    contains a JSON object with ``type: "content"`` or ``type: "done"``.
    """
    await get_conversation(body.conversation_id, user, db)

    return StreamingResponse(
        chat_service.stream_message(
            user_id=user.id,
            conversation_id=body.conversation_id,
            content=body.content,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/regenerate")
async def regenerate_message(body: RegenerateRequest, user: CurrentUser, db: DBSession):
    """Regenerate the last AI response.

    Finds the last user message, deletes the last assistant message,
    and re-runs the graph to produce a new response.
    """
    await get_conversation(body.conversation_id, user, db)

    # Find the last user message
    msgs = (
        await db.execute(
            select(Message)
            .where(Message.conversation_id == body.conversation_id)
            .order_by(Message.created_at.desc())
            .limit(2)
        )
    ).scalars().all()

    if not msgs:
        raise HTTPException(status_code=400, detail="No messages to regenerate")

    # If last message is assistant, delete it; get the user message before it
    if msgs[0].role == "assistant":
        await db.delete(msgs[0])
        await db.flush()
        user_content = msgs[1].content if len(msgs) > 1 and msgs[1].role == "user" else None
    elif msgs[0].role == "user":
        user_content = msgs[0].content
    else:
        raise HTTPException(status_code=400, detail="Cannot regenerate")

    if not user_content:
        raise HTTPException(status_code=400, detail="No user message found to regenerate from")

    return StreamingResponse(
        chat_service.stream_message(
            user_id=user.id,
            conversation_id=body.conversation_id,
            content=user_content,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.websocket("/ws/{conversation_id}")
async def websocket_chat(websocket: WebSocket, conversation_id: str):
    """WebSocket endpoint for real-time bidirectional chat.

    Protocol:
    - Client sends: {"content": "..."}
    - Server sends: {"type": "content"|"done"|"error", ...}
    """
    await websocket.accept()

    # NOTE: In production you'd validate the JWT from the WS handshake
    # (query param or first message). Simplified here.
    try:
        while True:
            data = await websocket.receive_json()
            content = data.get("content", "")
            if not content:
                await websocket.send_json({"type": "error", "detail": "Empty content"})
                continue

            # Stream response chunks
            async for chunk in chat_service.stream_message(
                user_id=data.get("user_id", "unknown"),
                conversation_id=conversation_id,
                content=content,
            ):
                # chunk is an SSE string like "data: {...}\n\n"
                text = chunk.strip()
                if text.startswith("data: "):
                    payload = json.loads(text[6:])
                    await websocket.send_json(payload)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_json({"type": "error", "detail": str(exc)})
        except Exception:
            pass


@router.post("/feedback", response_model=MessageFeedbackResponse, status_code=status.HTTP_201_CREATED)
async def submit_feedback(body: MessageFeedbackRequest, user: CurrentUser, db: DBSession):
    """Submit thumb-up/down feedback for a message."""
    # Verify message exists
    msg = (
        await db.execute(select(Message).where(Message.id == body.message_id))
    ).scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    fb = await chat_service.save_feedback(
        db, body.message_id, body.feedback_type, body.comment
    )
    return fb


@router.get("/history", response_model=PaginatedResponse)
async def get_history(
    conversation_id: str = Query(...),
    before_id: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    user: CurrentUser = ...,
    db: DBSession = ...,
):
    """Fetch paginated message history for a conversation."""
    # Verify ownership
    from app.api.deps import get_conversation as _gc
    await _gc(conversation_id, user, db)

    messages = await chat_service.get_history(db, conversation_id, before_id, limit)
    return PaginatedResponse(
        items=messages,
        total=len(messages),
        page=1,
        page_size=limit,
        has_next=len(messages) == limit,
    )


@router.get("/turns/{turn_id}/agents", response_model=list[AgentTurnLogResponse])
async def get_turn_agent_logs(
    turn_id: str,
    user: CurrentUser,
    db: DBSession,
):
    """List all agent invocations for a single turn.

    Validates ownership by JOINing AgentExecutionLog → Conversation and
    ensuring Conversation.user_id matches the current user.
    """
    rows = (
        await db.execute(
            select(AgentExecutionLog)
            .join(
                Conversation,
                Conversation.id == AgentExecutionLog.conversation_id,
            )
            .where(
                AgentExecutionLog.turn_id == turn_id,
                Conversation.user_id == user.id,
            )
            .order_by(AgentExecutionLog.created_at.asc())
        )
    ).scalars().all()

    return [
        AgentTurnLogResponse(
            agent_name=row.agent_name,
            started_at=row.created_at,
            duration_ms=row.execution_time_ms,
            is_focus=False,
            output=row.output_payload,
        )
        for row in rows
    ]
