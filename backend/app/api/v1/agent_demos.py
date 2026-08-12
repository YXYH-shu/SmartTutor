"""Read-only demo endpoints for individual agents."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DBSession
from app.api.schemas import (
    ResourceRecommendationDemoResponse,
    ResourceRecommendationDemoScenario,
    StudyBuddyDemoResponse,
    StudyBuddyDemoScenario,
)
from app.models.learning_resource import LearningResource
from app.models.user import User
from app.services.agents import get_agent

router = APIRouter(prefix="/agent-demos", tags=["agent-demos"])

_REQUIRED_RESOURCE_IDS = {
    "phys-force-sim-002",
    "phys-newton-quiz-003",
}
_REQUIRED_STUDY_BUDDY_IDS = {
    "test-buddy-newton",
    "test-buddy-induction",
    "test-buddy-mechanics",
    "test-buddy-physics",
}

_DEMO_SCENARIO = ResourceRecommendationDemoScenario(
    message="请在牛顿运动定律类似的两个资源",
    target_knowledge="牛顿运动定律",
    difficulty="中级",
)
_STUDY_BUDDY_DEMO_SCENARIO = StudyBuddyDemoScenario(
    message="请推荐两个可以一起学习物理的学伴",
)


async def _has_demo_resources(db: Any) -> bool:
    rows = (
        await db.execute(
            select(LearningResource.id).where(LearningResource.id.in_(_REQUIRED_RESOURCE_IDS))
        )
    ).scalars().all()
    return _REQUIRED_RESOURCE_IDS.issubset(set(rows))


async def _has_demo_study_buddies(db: Any) -> bool:
    rows = (
        await db.execute(
            select(User.id).where(User.id.in_(_REQUIRED_STUDY_BUDDY_IDS), User.is_active.is_(True))
        )
    ).scalars().all()
    return _REQUIRED_STUDY_BUDDY_IDS.issubset(set(rows))


async def _resolve_demo_user_id(db: Any, user_id: str | None) -> str:
    if user_id:
        return user_id
    demo_user_id = (
        await db.execute(select(User.id).order_by(User.created_at).limit(1))
    ).scalars().first()
    if demo_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="演示用户未初始化，请先创建至少一个用户。",
        )
    return str(demo_user_id)


@router.post(
    "/resource-recommender/run",
    response_model=ResourceRecommendationDemoResponse,
)
async def run_resource_recommender_demo(
    db: DBSession,
    user_id: str | None = None,
) -> ResourceRecommendationDemoResponse:
    """Run the real resource recommender with a fixed, non-persistent scenario."""
    if not await _has_demo_resources(db):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="演示资源未初始化，请先导入物理资源数据。",
        )
    demo_user_id = await _resolve_demo_user_id(db, user_id)

    agent = get_agent("resource_recommender")
    result = await agent.execute(
        input_data={
            "user_id": demo_user_id,
            "current_message": _DEMO_SCENARIO.message,
            "recent_messages": [],
            "stage": "resource_recommendation_demo",
            "target_knowledge": _DEMO_SCENARIO.target_knowledge,
            "difficulty": _DEMO_SCENARIO.difficulty,
            "learning_style": "交互式学习",
            "diagnosis_result": {
                "weak_points": [_DEMO_SCENARIO.target_knowledge],
                "mastery_rates": {_DEMO_SCENARIO.target_knowledge: 0.45},
            },
        },
        context={
            "user_id": demo_user_id,
            "persist_recommendation": False,
            "log_execution": False,
            "demo_mode": True,
        },
    )

    return ResourceRecommendationDemoResponse(
        scenario=_DEMO_SCENARIO,
        output=result.get("output", {}),
        usage=result.get("usage", {}),
        latency_ms=int(result.get("latency_ms", 0)),
    )


@router.post(
    "/study-buddy/run",
    response_model=StudyBuddyDemoResponse,
)
async def run_study_buddy_demo(
    db: DBSession,
    user_id: str | None = None,
) -> StudyBuddyDemoResponse:
    """Run the real study-buddy recommender with a fixed, non-persistent scenario."""
    if not await _has_demo_study_buddies(db):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="演示学伴用户未初始化，请先创建测试学伴用户。",
        )
    demo_user_id = await _resolve_demo_user_id(db, user_id)

    agent = get_agent("study_buddy")
    result = await agent.execute(
        input_data={
            "user_id": demo_user_id,
            "current_message": _STUDY_BUDDY_DEMO_SCENARIO.message,
            "recent_messages": [],
            "stage": "study_buddy_demo",
            "learning_style": "探究式",
            "diagnosis_result": {
                "weak_points": ["电磁感应与楞次定律"],
                "mastery_rates": {"牛顿运动定律": 0.45},
            },
        },
        context={
            "user_id": demo_user_id,
            "persist_recommendation": False,
            "log_execution": False,
            "demo_mode": True,
        },
    )

    return StudyBuddyDemoResponse(
        scenario=_STUDY_BUDDY_DEMO_SCENARIO,
        output=result.get("output", {}),
        usage=result.get("usage", {}),
        latency_ms=int(result.get("latency_ms", 0)),
    )
