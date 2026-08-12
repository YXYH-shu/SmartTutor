"""Contract tests for direct, non-persistent recommendation demonstrations."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_db
from app.api.v1.agent_demos import router


class _ScalarRows:
    def __init__(self, rows: list[str]) -> None:
        self._rows = rows

    def all(self) -> list[str]:
        return self._rows

    def first(self) -> str | None:
        return self._rows[0] if self._rows else None


class _QueryResult:
    def __init__(self, rows: list[str]) -> None:
        self._rows = rows

    def scalars(self) -> _ScalarRows:
        return _ScalarRows(self._rows)


class _DemoAgent:
    def __init__(self) -> None:
        self.execute = AsyncMock(
            return_value={
                "output": {
                    "recommendation_text": "推荐物理交互实验和随堂测验。",
                    "plan_history": [{"need_tool": True, "target_count": 2}],
                    "tool_trace": [{"tool": "RankingTool", "status": "executed", "count": 2}],
                    "reflection_history": [{"passed": True}],
                    "resources": [],
                },
                "usage": {"total_tokens": 42},
                "latency_ms": 321,
            }
        )


class _StudyBuddyDemoAgent:
    def __init__(self) -> None:
        self.execute = AsyncMock(
            return_value={
                "output": {
                    "recommendation_text": "推荐两位物理学习伙伴。",
                    "plan_history": [{"need_tool": True, "target_count": 2}],
                    "tool_trace": [{"tool": "RankingTool", "status": "executed", "count": 2}],
                    "reflection_history": [{"passed": True}],
                    "buddies": [],
                },
                "usage": {"total_tokens": 42},
                "latency_ms": 321,
            }
        )


def _app_with_overrides(resource_ids: list[str], user_ids: list[str] | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    class DemoDb:
        def __init__(self):
            self.calls = 0

        async def execute(self, _query):
            self.calls += 1
            return _QueryResult(resource_ids if self.calls == 1 else (user_ids or ["demo-user"]))

    async def db_session():
        yield DemoDb()

    app.dependency_overrides[get_db] = db_session
    return app


def _buddy_app_with_overrides(buddy_ids: list[str], user_ids: list[str] | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    class DemoDb:
        def __init__(self):
            self.calls = 0

        async def execute(self, _query):
            self.calls += 1
            return _QueryResult(buddy_ids if self.calls == 1 else (user_ids or ["demo-user"]))

    async def db_session():
        yield DemoDb()

    app.dependency_overrides[get_db] = db_session
    return app


@pytest.mark.asyncio
async def test_demo_endpoint_allows_anonymous_requests(monkeypatch):
    agent = _DemoAgent()
    monkeypatch.setattr("app.api.v1.agent_demos.get_agent", lambda name: agent)
    app = _app_with_overrides(["phys-force-sim-002", "phys-newton-quiz-003"])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/agent-demos/resource-recommender/run")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_demo_endpoint_runs_fixed_non_persistent_context(monkeypatch):
    agent = _DemoAgent()
    monkeypatch.setattr("app.api.v1.agent_demos.get_agent", lambda name: agent)
    app = _app_with_overrides(["phys-force-sim-002", "phys-newton-quiz-003"])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/agent-demos/resource-recommender/run")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scenario"]["message"] == "请在牛顿运动定律类似的两个资源"
    assert payload["usage"] == {"total_tokens": 42}
    assert payload["latency_ms"] == 321
    assert payload["output"]["tool_trace"][0]["tool"] == "RankingTool"

    input_data = agent.execute.await_args.kwargs["input_data"]
    context = agent.execute.await_args.kwargs["context"]
    assert input_data["current_message"] == "请在牛顿运动定律类似的两个资源"
    assert input_data["user_id"] == "demo-user"
    assert input_data["recent_messages"] == []
    assert context["persist_recommendation"] is False
    assert context["log_execution"] is False


@pytest.mark.asyncio
async def test_demo_endpoint_rejects_missing_seed_resources(monkeypatch):
    get_agent = MagicMock()
    monkeypatch.setattr("app.api.v1.agent_demos.get_agent", get_agent)
    app = _app_with_overrides(["phys-force-sim-002"])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/agent-demos/resource-recommender/run")

    assert response.status_code == 409
    assert "演示资源未初始化" in response.json()["detail"]
    get_agent.assert_not_called()


@pytest.mark.asyncio
async def test_study_buddy_demo_endpoint_allows_anonymous_non_persistent_run(monkeypatch):
    agent = _StudyBuddyDemoAgent()
    monkeypatch.setattr("app.api.v1.agent_demos.get_agent", lambda name: agent)
    app = _buddy_app_with_overrides(
        ["test-buddy-newton", "test-buddy-induction", "test-buddy-mechanics", "test-buddy-physics"]
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/agent-demos/study-buddy/run")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scenario"]["message"] == "请推荐两个可以一起学习物理的学伴"
    assert payload["usage"] == {"total_tokens": 42}
    input_data = agent.execute.await_args.kwargs["input_data"]
    context = agent.execute.await_args.kwargs["context"]
    assert input_data["user_id"] == "demo-user"
    assert input_data["current_message"] == payload["scenario"]["message"]
    assert context["persist_recommendation"] is False
    assert context["log_execution"] is False


@pytest.mark.asyncio
async def test_study_buddy_demo_rejects_missing_test_users(monkeypatch):
    get_agent = MagicMock()
    monkeypatch.setattr("app.api.v1.agent_demos.get_agent", get_agent)
    app = _buddy_app_with_overrides(["test-buddy-newton"])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/agent-demos/study-buddy/run")

    assert response.status_code == 409
    assert "演示学伴用户未初始化" in response.json()["detail"]
    get_agent.assert_not_called()


@pytest.mark.asyncio
async def test_demo_execution_skips_recommendation_and_execution_logs():
    from app.services.agents.resource_recommender import ResourceRecommenderAgent

    agent = ResourceRecommenderAgent(llm=MagicMock())
    agent.enrich_input = AsyncMock(side_effect=lambda data, _context: data)
    agent._generate_plan = AsyncMock(
        return_value=(
            {
                "need_tool": False,
                "target_count": 0,
                "recall_strategy": "无需工具",
                "ranking_criteria": [],
            },
            {},
        )
    )
    agent._summary = AsyncMock(
        return_value=(
            {
                "recommendation_text": "已生成演示推荐。",
                "planning": {"target_count": 0},
                "resources": [],
                "rationale": "演示",
                "sequence": [],
                "reflection": {},
                "tool_trace": [],
            },
            {},
        )
    )
    agent._persist_recommendation = AsyncMock(return_value="unexpected-id")
    agent._log_execution = AsyncMock()
    agent.post_process = AsyncMock()

    result = await agent.execute(
        {"current_message": "帮我推荐几个物理资源", "recent_messages": []},
        context={"persist_recommendation": False, "log_execution": False},
    )

    agent._persist_recommendation.assert_not_awaited()
    agent._log_execution.assert_not_awaited()
    assert "recommendation_id" not in result["output"]
