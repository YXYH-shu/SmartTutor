"""Conversation routes – CRUD operations."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DBSession, get_conversation
from app.api.schemas import (
    ConversationCreateRequest,
    ConversationDetailResponse,
    ConversationResponse,
    MessageResponse,
    PaginatedResponse,
    SessionQuestionnaireRequest,
    SessionQuestionnaireResponse,
    TitleUpdateRequest,
)
from app.models.session_feedback import SessionFeedback
from app.services import conversation_service

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=PaginatedResponse)
async def list_conversations(
    user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List conversations for the current user (paginated, newest first)."""
    items, total = await conversation_service.list_conversations(
        db, user.id, page=page, page_size=page_size
    )
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=(page * page_size) < total,
    )


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: ConversationCreateRequest,
    user: CurrentUser,
    db: DBSession,
):
    """Create a new conversation.  Workflow type is auto-inferred if not specified."""
    conv = await conversation_service.create_conversation(
        db,
        user.id,
        title=body.title or "新对话",
        workflow_type=body.workflow_type,
    )
    return conv


@router.get("/{conversation_id}")
async def get_conversation_detail(
    conversation_id: str,
    user: CurrentUser,
    db: DBSession,
    limit: int = Query(50, ge=1, le=200),
    before_id: str | None = None,
):
    """Fetch a conversation with its messages."""
    # Verify ownership
    conv = await get_conversation(conversation_id, user, db)
    detail = await conversation_service.get_conversation_detail(
        db, conv.id, message_limit=limit, before_id=before_id
    )
    if not detail:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return detail


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    user: CurrentUser,
    db: DBSession,
):
    """Soft-delete a conversation."""
    await get_conversation(conversation_id, user, db)
    await conversation_service.soft_delete(db, conversation_id)
    return None


@router.put("/{conversation_id}/title", response_model=dict)
async def update_title(
    conversation_id: str,
    body: TitleUpdateRequest,
    user: CurrentUser,
    db: DBSession,
):
    """Rename a conversation."""
    await get_conversation(conversation_id, user, db)
    await conversation_service.update_title(db, conversation_id, body.title)
    return {"id": conversation_id, "title": body.title}


# ── Session end / questionnaire ───────────────────────────────────────


@router.post(
    "/{conversation_id}/questionnaire",
    response_model=SessionQuestionnaireResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_session_questionnaire(
    conversation_id: str,
    body: SessionQuestionnaireRequest,
    user: CurrentUser,
    db: DBSession,
):
    """Submit the end-of-session 3-question Likert questionnaire."""
    conv = await get_conversation(conversation_id, user, db)

    if conv.ended_at is not None:
        raise HTTPException(status_code=409, detail="该会话已提交过问卷")

    existing = (
        await db.execute(
            select(SessionFeedback).where(SessionFeedback.conversation_id == conv.id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="该会话已提交过问卷")

    if await conversation_service.count_user_messages(db, conv.id) == 0:
        raise HTTPException(status_code=400, detail="会话暂无对话记录，无需填写问卷")

    fb = await conversation_service.submit_session_questionnaire(
        db, conv, body.q1_score, body.q2_score, body.q3_score
    )
    return fb


@router.post("/{conversation_id}/end", response_model=ConversationResponse)
async def end_conversation(
    conversation_id: str,
    user: CurrentUser,
    db: DBSession,
):
    """End a tutoring session (idempotent).

    A conversation with user messages must have its questionnaire submitted
    before it can be ended.
    """
    conv = await get_conversation(conversation_id, user, db)

    if conv.ended_at is None:
        has_messages = await conversation_service.count_user_messages(db, conv.id) > 0
        has_feedback = (
            await db.execute(
                select(SessionFeedback).where(SessionFeedback.conversation_id == conv.id)
            )
        ).scalar_one_or_none() is not None
        if has_messages and not has_feedback:
            raise HTTPException(
                status_code=400,
                detail="该会话存在对话记录，需先提交会话体验问卷才能结束",
            )
        conv = await conversation_service.end_conversation(db, conv)

    return conv


@router.get("/questionnaires/export")
async def export_questionnaires(
    user: CurrentUser,
    db: DBSession,
    format: str = Query("csv", pattern="^(csv|json)$"),
):
    """Export all submitted session questionnaires as CSV or JSON."""
    rows = (
        await db.execute(select(SessionFeedback).order_by(SessionFeedback.created_at.asc()))
    ).scalars().all()

    if format == "json":
        return {
            "items": [
                SessionQuestionnaireResponse.model_validate(r).model_dump()
                for r in rows
            ]
        }

    lines = [
        "conversation_id,user_id,q1_score,q2_score,q3_score,total_score,created_at,acceptable"
    ]
    for r in rows:
        acceptable = 1 if r.total_score >= 7 else 0
        lines.append(
            f"{r.conversation_id},{r.user_id},{r.q1_score},{r.q2_score},"
            f"{r.q3_score},{r.total_score},{r.created_at.isoformat()},{acceptable}"
        )
    csv_str = "\n".join(lines) + "\n"
    return Response(
        content=csv_str,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=session_questionnaires.csv"},
    )
