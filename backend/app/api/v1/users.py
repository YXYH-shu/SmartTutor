"""User routes – profile and stats."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DBSession, CurrentUser
from app.api.schemas import (
    KnowledgeGraphEdge,
    KnowledgeGraphNode,
    KnowledgeGraphResponse,
    ProfileResponse,
    ProfileUpdateRequest,
    UserStatsResponse,
)
from app.models.conversation import Conversation
from app.models.knowledge_knowledge import KnowledgeKnowledge
from app.models.knowledge_point import KnowledgePoint
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


@router.get("/knowledge-graph", response_model=KnowledgeGraphResponse)
async def get_user_knowledge_graph(user: CurrentUser, db: DBSession):
    """Return the knowledge graph relevant to this user.

    Strategy: read the user's flat mastery dict (UserProfile.knowledge_graph
    ``{skill_id_or_kp_id: 0..1}``) and only return nodes whose id appears in
    that dict. Edges are limited to those connecting the returned nodes. This
    keeps the response small even when the full knowledge_points table is
    large.
    """
    profile = (
        await db.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        )
    ).scalar_one_or_none()
    mastery: dict[str, float] = (
        profile.knowledge_graph if profile and profile.knowledge_graph else {}
    )

    node_ids = set(mastery.keys())

    nodes: list[KnowledgeGraphNode] = []
    edges: list[KnowledgeGraphEdge] = []

    if node_ids:
        # Load matching knowledge_points (cap at 200 to bound payload).
        kp_rows = (
            await db.execute(
                select(KnowledgePoint.id, KnowledgePoint.name).where(
                    KnowledgePoint.id.in_(node_ids)
                )
            )
        ).all()
        known_ids = {row.id for row in kp_rows}
        for row in kp_rows:
            score = mastery.get(row.id)
            nodes.append(
                KnowledgeGraphNode(
                    id=row.id,
                    label=row.name or row.id,
                    mastery=float(score) if score is not None else None,
                    status=_status_for(score),
                )
            )

        # Edges between nodes that are both in our set.
        edge_rows = (
            await db.execute(
                select(
                    KnowledgeKnowledge.source_kp_id,
                    KnowledgeKnowledge.target_kp_id,
                ).where(
                    KnowledgeKnowledge.source_kp_id.in_(node_ids),
                    KnowledgeKnowledge.target_kp_id.in_(node_ids),
                )
            )
        ).all()
        for row in edge_rows:
            edges.append(KnowledgeGraphEdge(source=row[0], target=row[1]))

        # Pull in a few ancestors/parents so the graph stays connected.
        # Limit to nodes whose parent is already shown.
        parent_rows = (
            await db.execute(
                select(KnowledgePoint.id, KnowledgePoint.name, KnowledgePoint.parent_knowledge)
                .where(KnowledgePoint.id.in_(node_ids))
            )
        ).all()
        missing_parent_ids = {
            r.parent_knowledge
            for r in parent_rows
            if r.parent_knowledge and r.parent_knowledge not in known_ids
        }
        if missing_parent_ids:
            parents = (
                await db.execute(
                    select(KnowledgePoint.id, KnowledgePoint.name).where(
                        KnowledgePoint.id.in_(missing_parent_ids)
                    )
                )
            ).all()
            for p in parents:
                nodes.append(
                    KnowledgeGraphNode(id=p.id, label=p.name or p.id, mastery=None, status=None)
                )
                edges.append(KnowledgeGraphEdge(source=p.id, target=p.id))

    return KnowledgeGraphResponse(nodes=nodes, edges=edges)


def _status_for(score: float | None) -> str | None:
    """Map mastery 0..1 to a coarse learning status label."""
    if score is None:
        return None
    if score >= 0.8:
        return "mastered"
    if score >= 0.5:
        return "learning"
    return "weak"
