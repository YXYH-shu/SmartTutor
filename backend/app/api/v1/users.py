"""User routes – profile and stats."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DBSession, CurrentUser
from app.api.schemas import (
    ProfileResponse,
    ProfileUpdateRequest,
    UserStatsResponse,
)
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user_profile import UserProfile

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(user: CurrentUser, db: DBSession):
    """Fetch the authenticated user's learning profile."""
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.put("/profile", response_model=ProfileResponse)
async def update_profile(body: ProfileUpdateRequest, user: CurrentUser, db: DBSession):
    """Update learning-style, level or preferences (partial update)."""
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    if body.learning_style is not None:
        profile.learning_style = body.learning_style
    if body.current_level is not None:
        profile.current_level = body.current_level
    if body.preferences is not None:
        prefs = profile.preferences or {}
        prefs.update(body.preferences)
        profile.preferences = prefs

    db.add(profile)
    await db.flush()
    return profile


@router.get("/stats", response_model=UserStatsResponse)
async def get_stats(user: CurrentUser, db: DBSession):
    """Learning statistics for the current user."""
    # Total conversations
    conv_count = (
        await db.execute(
            select(func.count()).select_from(Conversation).where(
                Conversation.user_id == user.id
            )
        )
    ).scalar() or 0

    # Total messages
    msg_count = (
        await db.execute(
            select(func.count())
            .select_from(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(Conversation.user_id == user.id)
        )
    ).scalar() or 0

    # Knowledge points from profile
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    knowledge_points = len(profile.knowledge_graph) if profile and profile.knowledge_graph else 0

    # Streak days (simplified: count distinct days with messages in last 30 days)
    streak = (
        await db.execute(
            select(func.count(func.distinct(func.date(Message.created_at))))
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(
                Conversation.user_id == user.id,
                Message.role == "user",
            )
        )
    ).scalar() or 0

    return UserStatsResponse(
        total_conversations=conv_count,
        total_messages=msg_count,
        knowledge_points_count=knowledge_points,
        streak_days=min(streak, 30),
    )
