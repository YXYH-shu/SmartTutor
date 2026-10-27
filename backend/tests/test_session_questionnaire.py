"""End-to-end tests for session end + 3-question Likert questionnaire."""

from __future__ import annotations

import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  – register all models on Base.metadata
from app.api.deps import get_current_user, get_db
from app.api.v1.conversations import router
from app.database import Base
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def env(
    db_session: AsyncSession,
) -> AsyncGenerator[tuple[AsyncClient, AsyncSession, User], None]:
    user = User(
        id=str(uuid.uuid4()),
        username="tester",
        email="tester@example.com",
        hashed_password="x",
    )
    db_session.add(user)
    await db_session.commit()

    app = FastAPI()
    app.include_router(router)

    async def override_db():
        yield db_session

    async def override_user():
        return user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, db_session, user


async def _make_conversation(
    db: AsyncSession, user_id: str, *, user_messages: int = 0
) -> Conversation:
    conv = Conversation(
        id=str(uuid.uuid4()),
        user_id=user_id,
        title="会话",
        workflow_type="adaptive_learning",
    )
    db.add(conv)
    for i in range(user_messages):
        db.add(
            Message(
                id=str(uuid.uuid4()),
                conversation_id=conv.id,
                role="user",
                content=f"第{i}条消息",
            )
        )
    await db.commit()
    await db.refresh(conv)
    return conv


@pytest.mark.asyncio
async def test_questionnaire_on_empty_conversation_rejected(env):
    ac, db, user = env
    conv = await _make_conversation(db, user.id)

    resp = await ac.post(
        f"/conversations/{conv.id}/questionnaire",
        json={"q1_score": 2, "q2_score": 2, "q3_score": 2},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "会话暂无对话记录，无需填写问卷"


@pytest.mark.asyncio
async def test_end_with_messages_without_questionnaire_rejected(env):
    ac, db, user = env
    conv = await _make_conversation(db, user.id, user_messages=2)

    resp = await ac.post(f"/conversations/{conv.id}/end")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "该会话存在对话记录，需先提交会话体验问卷才能结束"

    await db.refresh(conv)
    assert conv.ended_at is None


@pytest.mark.asyncio
async def test_questionnaire_submit_201_and_ends_conversation(env):
    ac, db, user = env
    conv = await _make_conversation(db, user.id, user_messages=3)

    resp = await ac.post(
        f"/conversations/{conv.id}/questionnaire",
        json={"q1_score": 3, "q2_score": 2, "q3_score": 3},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["conversation_id"] == conv.id
    assert body["q1_score"] == 3
    assert body["total_score"] == 8

    await db.refresh(conv)
    assert conv.ended_at is not None


@pytest.mark.asyncio
async def test_duplicate_questionnaire_rejected_409(env):
    ac, db, user = env
    conv = await _make_conversation(db, user.id, user_messages=1)
    resp = await ac.post(
        f"/conversations/{conv.id}/questionnaire",
        json={"q1_score": 2, "q2_score": 2, "q3_score": 2},
    )
    assert resp.status_code == 201

    resp = await ac.post(
        f"/conversations/{conv.id}/questionnaire",
        json={"q1_score": 1, "q2_score": 1, "q3_score": 1},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "该会话已提交过问卷"


@pytest.mark.asyncio
async def test_end_allowed_after_questionnaire_and_idempotent(env):
    ac, db, user = env
    conv = await _make_conversation(db, user.id, user_messages=1)
    await ac.post(
        f"/conversations/{conv.id}/questionnaire",
        json={"q1_score": 3, "q2_score": 3, "q3_score": 3},
    )

    resp = await ac.post(f"/conversations/{conv.id}/end")
    assert resp.status_code == 200
    ended_at = resp.json()["ended_at"]
    assert ended_at is not None

    # Idempotent – second call returns the same ended_at
    resp = await ac.post(f"/conversations/{conv.id}/end")
    assert resp.status_code == 200
    assert resp.json()["ended_at"] == ended_at


@pytest.mark.asyncio
async def test_export_csv_and_json(env):
    ac, db, user = env
    conv = await _make_conversation(db, user.id, user_messages=1)
    await ac.post(
        f"/conversations/{conv.id}/questionnaire",
        json={"q1_score": 3, "q2_score": 3, "q3_score": 1},
    )

    resp = await ac.get("/conversations/questionnaires/export", params={"format": "csv"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    lines = resp.text.strip().splitlines()
    assert lines[0] == (
        "conversation_id,user_id,q1_score,q2_score,q3_score,total_score,created_at,acceptable"
    )
    assert len(lines) == 2
    fields = lines[1].split(",")
    assert fields[5] == "7"  # 3 + 3 + 1
    assert fields[7] == "1"  # total >= 7 → acceptable

    resp = await ac.get("/conversations/questionnaires/export", params={"format": "json"})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["conversation_id"] == conv.id
    assert items[0]["total_score"] == 7
