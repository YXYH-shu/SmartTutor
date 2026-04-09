"""Conversation routes – CRUD operations."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DBSession, get_conversation
from app.api.schemas import (
    ConversationCreateRequest,
    ConversationDetailResponse,
    ConversationResponse,
    MessageResponse,
    PaginatedResponse,
    TitleUpdateRequest,
)
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
