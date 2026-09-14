"""Contract tests for POST /internal/v1/processTutoringInteraction.

覆盖：公共请求头校验(200001)、apiVersion(200002)、请求体校验(200001)、
未知 processingStage(200002)、两扩展阶段成功映射（小驼峰）、
模型失败降级(degraded)、requestId 回显。agent 在 handler 边界 mock，
不发真实 LLM 请求。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.api.internal import internal_router  # noqa: E402
import app.api.internal.handlers as handlers  # noqa: E402
import app.api.internal.recommendations as recommendations  # noqa: E402
import app.middleware.rate_limiter as rate_limiter  # noqa: E402


HEADERS = {
    "appId": "kt5",
    "userId": "u-001",
    "requestId": "req-test-001",
    "apiVersion": "v1",
}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(internal_router)
    return TestClient(app)


def _mock_agent(version: str, output: dict[str, Any]) -> MagicMock:
    agent = MagicMock()
    agent.version = version
    agent.execute = AsyncMock(return_value={"output": output, "usage": {}, "latency_ms": 5})
    return agent


def _patch_agent(monkeypatch: pytest.MonkeyPatch, agent: MagicMock) -> MagicMock:
    """Patch handlers.get_agent so every call returns the SAME mock instance."""
    monkeypatch.setattr(handlers, "get_agent", lambda name: agent)
    return agent


def _failing_agent(version: str) -> MagicMock:
    agent = MagicMock()
    agent.version = version
    agent.execute = AsyncMock(side_effect=TimeoutError("vllm timeout"))
    return agent


# ---------------------------------------------------------------------------
# 请求头 / 请求体校验
# ---------------------------------------------------------------------------

def test_missing_headers_returns_200001() -> None:
    with _client() as client:
        resp = client.post("/internal/v1/processTutoringInteraction", json={})
    body = resp.json()
    assert resp.status_code == 200
    assert body["code"] == "200001"
    for h in ("appId", "userId", "requestId", "apiVersion"):
        assert h in body["message"]
    assert body["data"] == {}


def test_bad_api_version_returns_200002() -> None:
    headers = {**HEADERS, "apiVersion": "v2"}
    with _client() as client:
        resp = client.post(
            "/internal/v1/processTutoringInteraction", headers=headers, json={}
        )
    assert resp.json()["code"] == "200002"


def test_invalid_json_body_returns_200001() -> None:
    with _client() as client:
        resp = client.post(
            "/internal/v1/processTutoringInteraction",
            headers=HEADERS,
            content="not-json",
        )
    assert resp.json()["code"] == "200001"


def test_missing_processing_stage_returns_200001() -> None:
    with _client() as client:
        resp = client.post(
            "/internal/v1/processTutoringInteraction",
            headers=HEADERS,
            json={"data": {}},
        )
    assert resp.json()["code"] == "200001"


def test_unsupported_stage_returns_200002_with_allowed_values() -> None:
    with _client() as client:
        resp = client.post(
            "/internal/v1/processTutoringInteraction",
            headers=HEADERS,
            json={"processingStage": "preResponse", "data": {}},
        )
    body = resp.json()
    assert body["code"] == "200002"
    assert "emotionAnalysis" in body["message"]
    assert "empathyResponse" in body["message"]


def test_request_id_echoed_on_error() -> None:
    headers = {**HEADERS, "requestId": "req-echo-42"}
    with _client() as client:
        resp = client.post(
            "/internal/v1/processTutoringInteraction",
            headers=headers,
            json={},
        )
    assert resp.json()["requestId"] == "req-echo-42"


def test_internal_rate_limit_uses_contract_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    app.add_middleware(rate_limiter.RateLimiterMiddleware)

    @app.post("/internal/v1/processTutoringInteraction")
    async def _endpoint() -> dict[str, str]:
        return {"unexpected": "route execution"}

    monkeypatch.setattr(rate_limiter, "_is_limited", lambda key, limit: True)
    with TestClient(app) as client:
        response = client.post(
            "/internal/v1/processTutoringInteraction", headers=HEADERS, json={}
        )

    assert response.status_code == 200
    assert response.json() == {
        "code": "500001",
        "message": "接口限流，请稍后重试",
        "requestId": HEADERS["requestId"],
        "data": {"retryAfterMs": rate_limiter.WINDOW * 1000},
    }


# ---------------------------------------------------------------------------
# emotionAnalysis
# ---------------------------------------------------------------------------

def test_emotion_analysis_success(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = _patch_agent(
        monkeypatch,
        _mock_agent("2.0", {"emotion": "negative", "reason": "表现出挫败感"}),
    )
    payload = {
        "processingStage": "emotionAnalysis",
        "data": {
            "scenarioCode": "qaTutoring",
            "interactionContext": {
                "query": "这道题我又做错了",
                "draftAnswer": "我们来看一下错在哪里。",
                "history": [
                    {"role": "student", "content": "老师好"},
                    {"role": "teacher", "content": "你好"},
                ],
            },
            "userContext": {"stage": "primarySchool", "grade": "grade5"},
            "unknownFutureField": {"any": "shape"},
        },
        "ext": {"source": "pytest"},
    }
    with _client() as client:
        resp = client.post(
            "/internal/v1/processTutoringInteraction", headers=HEADERS, json=payload
        )
    body = resp.json()
    assert body["code"] == "000000"
    assert body["requestId"] == HEADERS["requestId"]
    emotion = body["data"]["emotion"]
    assert emotion["dominantEmotion"] == "negative"
    assert emotion["reason"] == "表现出挫败感"
    assert emotion["vad"] is None
    trace = body["data"]["trace"]
    assert trace["capabilityVersion"] == "2.0"
    assert trace["traceId"] and trace["processedAt"]

    agent_exec = agent.execute
    sent = agent.execute.call_args.kwargs["input_data"]
    # draftAnswer 进了对话历史（ai 侧），query 是 current_message
    assert sent["current_message"] == "这道题我又做错了"
    assert sent["message_history"][-1] == {"role": "ai", "content": "我们来看一下错在哪里。"}
    assert sent["message_history"][0] == {"role": "human", "content": "老师好"}


def test_emotion_analysis_missing_query_returns_200001(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        handlers, "get_agent", lambda name: _mock_agent("2.0", {})
    )
    payload = {
        "processingStage": "emotionAnalysis",
        "data": {"scenarioCode": "qaTutoring", "interactionContext": {}},
    }
    with _client() as client:
        resp = client.post(
            "/internal/v1/processTutoringInteraction", headers=HEADERS, json=payload
        )
    assert resp.json()["code"] == "200001"


def test_emotion_analysis_agent_failure_degrades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        handlers, "get_agent", lambda name: _failing_agent("2.0")
    )
    payload = {
        "processingStage": "emotionAnalysis",
        "data": {
            "scenarioCode": "qaTutoring",
            "interactionContext": {"query": "我烦死了"},
        },
    }
    with _client() as client:
        resp = client.post(
            "/internal/v1/processTutoringInteraction", headers=HEADERS, json=payload
        )
    body = resp.json()
    assert body["code"] == "000000"
    data = body["data"]
    assert data["degraded"] is True
    assert data["degradeReason"]
    assert data["availableResults"] == []
    assert "emotion" not in data


def test_emotion_analysis_unparseable_output_degrades(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        handlers, "get_agent", lambda name: _mock_agent("2.0", {"reason": "no emotion"})
    )
    payload = {
        "processingStage": "emotionAnalysis",
        "data": {
            "scenarioCode": "qaTutoring",
            "interactionContext": {"query": "今天天气如何"},
        },
    }
    with _client() as client:
        resp = client.post(
            "/internal/v1/processTutoringInteraction", headers=HEADERS, json=payload
        )
    assert resp.json()["data"]["degraded"] is True


# ---------------------------------------------------------------------------
# empathyResponse
# ---------------------------------------------------------------------------

def test_empathy_response_success(monkeypatch: pytest.MonkeyPatch) -> None:
    agent = _patch_agent(
        monkeypatch,
        _mock_agent(
            "1.0",
            {
                "empathetic_response": "别急，我们一步步来看。",
                "psychological_techniques": ["情感正常化"],
                "teacher_persona": "温和的引导者",
            },
        ),
    )
    payload = {
        "processingStage": "empathyResponse",
        "data": {
            "scenarioCode": "qaTutoring",
            "interactionContext": {
                "draftAnswer": "这道题的答案是B。",
                "query": "为什么选B？",
            },
            "emotion": {"dominantEmotion": "negative", "vad": None},
            "userContext": {
                "stage": "primarySchool",
                "grade": "grade5",
                "subject": "science",
                "learnerStateSummary": "电学薄弱",
            },
        },
    }
    with _client() as client:
        resp = client.post(
            "/internal/v1/processTutoringInteraction", headers=HEADERS, json=payload
        )
    body = resp.json()
    assert body["code"] == "000000"
    empathy = body["data"]["empathy"]
    assert empathy["empatheticResponse"] == "别急，我们一步步来看。"
    assert empathy["psychologicalTechniques"] == ["情感正常化"]
    assert empathy["teacherPersona"] == "温和的引导者"
    assert body["data"]["trace"]["capabilityVersion"] == "1.0"

    sent = agent.execute.call_args.kwargs["input_data"]
    assert sent["raw_response"] == "这道题的答案是B。"
    assert sent["emotion_state"] == {"dominantEmotion": "negative", "vad": None}
    assert sent["user_profile"]["learnerStateSummary"] == "电学薄弱"
    assert "qaTutoring" in sent["scenario"] and "为什么选B？" in sent["scenario"]
    assert sent["user_id"] == "u-001"


def test_empathy_response_missing_draft_answer_returns_200001(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        handlers, "get_agent", lambda name: _mock_agent("1.0", {})
    )
    payload = {
        "processingStage": "empathyResponse",
        "data": {"scenarioCode": "qaTutoring", "interactionContext": {}},
    }
    with _client() as client:
        resp = client.post(
            "/internal/v1/processTutoringInteraction", headers=HEADERS, json=payload
        )
    body = resp.json()
    assert body["code"] == "200001"
    assert "draftAnswer" in body["message"]


def test_empathy_response_agent_failure_degrades_without_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        handlers, "get_agent", lambda name: _failing_agent("1.0")
    )
    payload = {
        "processingStage": "empathyResponse",
        "data": {
            "scenarioCode": "qaTutoring",
            "interactionContext": {"draftAnswer": "答案是B。"},
        },
    }
    with _client() as client:
        resp = client.post(
            "/internal/v1/processTutoringInteraction", headers=HEADERS, json=payload
        )
    body = resp.json()
    assert body["code"] == "000000"
    data = body["data"]
    assert data["degraded"] is True
    assert "empathy" not in data


# ---------------------------------------------------------------------------
# 900000
# ---------------------------------------------------------------------------

def test_unexpected_handler_error_returns_900000(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(name: str) -> Any:
        raise RuntimeError("registry corrupted")

    monkeypatch.setattr(handlers, "get_agent", boom)
    payload = {
        "processingStage": "emotionAnalysis",
        "data": {
            "scenarioCode": "qaTutoring",
            "interactionContext": {"query": "你好"},
        },
    }
    with _client() as client:
        resp = client.post(
            "/internal/v1/processTutoringInteraction", headers=HEADERS, json=payload
        )
    body = resp.json()
    assert body["code"] == "900000"
    assert body["requestId"] == HEADERS["requestId"]


# ---------------------------------------------------------------------------
# learningSupport recommendation adapter
# ---------------------------------------------------------------------------

def _learning_support_payload(scenario_code: str) -> dict[str, Any]:
    return {
        "processingStage": "learningSupport",
        "data": {
            "scenarioCode": scenario_code,
            "userContext": {
                "stage": "seniorHighSchool",
                "grade": "grade10",
                "subject": "physics",
                "learnerStateSummary": "牛顿运动定律掌握不足",
            },
            "learningEvidence": [
                {
                    "knowledgePointId": "kp-newton-law",
                    "responseResult": "incorrect",
                    "occurredAt": "2026-09-13T09:00:00Z",
                }
            ],
        },
    }


def test_learning_support_resource_uses_agent_planning_without_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ResourceAgent:
        version = "resource-test"

        async def execute(
            self, input_data: dict[str, Any], context: dict[str, Any]
        ) -> dict[str, Any]:
            assert input_data["user_id"] == HEADERS["userId"]
            assert input_data["target_knowledge"] == ["kp-newton-law"]
            assert input_data["current_message"] == "Recommend a Newton law resource"
            assert input_data["recent_messages"] == [
                {"role": "student", "content": "I still cannot distinguish force and acceleration."},
                {"role": "assistant", "content": "Try a targeted quiz next."},
                {"role": "assistant", "content": "The learner previously received a basic explanation."},
            ]
            assert input_data["draft_answer"] == "The learner previously received a basic explanation."
            assert input_data["history_resource_ids"] == ["res-1"]
            assert context == {"persist_recommendation": False, "log_execution": False}
            return {
                "output": {
                    "resources": [
                        {"id": "res-1", "title": "匀速直线运动", "type": "video"}
                    ],
                    "execution_context": {"ranking": {"ranking_backend": "graph"}},
                }
            }

    monkeypatch.setattr(recommendations, "get_agent", lambda name: ResourceAgent())

    payload = _learning_support_payload("resourceRecommendation")
    payload["data"]["interactionContext"] = {
        "query": "Recommend a Newton law resource",
        "draftAnswer": "The learner previously received a basic explanation.",
        "history": [
            {
                "role": "student",
                "content": "I still cannot distinguish force and acceleration.",
                "resourceId": "res-1",
            },
            {"role": "assistant", "text": "Try a targeted quiz next."},
        ],
    }
    with _client() as client:
        response = client.post(
            "/internal/v1/processTutoringInteraction", headers=HEADERS, json=payload
        )

    body = response.json()
    assert body["code"] == "000000"
    assert [item["resourceId"] for item in body["data"]["recommendations"]] == ["res-1"]


def test_learning_support_resource_candidates_bypass_planning_and_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = MagicMock()
    agent.version = "resource-test"
    agent.execute = AsyncMock()
    agent._load_all_resource_candidates = AsyncMock()
    agent._rows_to_resource_candidates = AsyncMock(
        return_value=[{"id": "res-2", "title": "候选资源"}]
    )
    agent._ranking_tool = AsyncMock(
        return_value=(
            [{"id": "res-2", "title": "候选资源", "graph_score": 0.91}],
            [{"id": "res-2", "title": "候选资源"}],
            {"ranking_backend": "graph"},
        )
    )
    monkeypatch.setattr(recommendations, "get_agent", lambda name: agent)

    payload = _learning_support_payload("resourceRecommendation")
    payload["data"]["candidateResources"] = [{"resourceId": "res-2"}]
    payload["data"]["interactionContext"] = {"history": [{"resourceId": "res-1"}]}
    with _client() as client:
        response = client.post(
            "/internal/v1/processTutoringInteraction", headers=HEADERS, json=payload
        )

    assert response.json()["code"] == "000000"
    assert [item["resourceId"] for item in response.json()["data"]["recommendations"]] == ["res-2"]
    agent._rows_to_resource_candidates.assert_awaited_once_with([{"resource_id": "res-2"}])
    ranking_input = agent._ranking_tool.await_args.args[2]
    assert ranking_input["history_resource_ids"] == ["res-1"]
    agent.execute.assert_not_awaited()
    agent._load_all_resource_candidates.assert_not_awaited()


def test_learning_support_study_buddy_uses_agent_planning_without_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StudyBuddyAgent:
        version = "buddy-test"

        async def execute(
            self, input_data: dict[str, Any], context: dict[str, Any]
        ) -> dict[str, Any]:
            assert input_data["user_id"] == HEADERS["userId"]
            assert input_data["history_user_ids"] == ["buddy-001"]
            assert context == {"persist_recommendation": False, "log_execution": False}
            return {
                "output": {
                    "buddies": [
                        {
                            "user_id": "buddy-002",
                            "nickname": "小明",
                            "complement_score": 0.88,
                        }
                    ],
                    "execution_context": {"ranking": {"ranking_backend": "graph"}},
                }
            }

    monkeypatch.setattr(recommendations, "get_agent", lambda name: StudyBuddyAgent())

    payload = _learning_support_payload("studyBuddyRecommendation")
    payload["data"]["interactionContext"] = {"history": [{"userId": "buddy-001"}]}
    with _client() as client:
        response = client.post(
            "/internal/v1/processTutoringInteraction", headers=HEADERS, json=payload
        )

    body = response.json()
    assert body["code"] == "000000"
    assert body["data"]["recommendations"] == []
    buddies = body["data"]["ext"]["studyBuddyRecommendation"]["buddies"]
    assert buddies[0]["userId"] == "buddy-002"


def test_learning_support_study_buddy_candidates_bypass_planning_and_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = MagicMock()
    agent.version = "buddy-test"
    agent.execute = AsyncMock()
    agent._fetch_buddy_details = AsyncMock(
        return_value=[{"user_id": "buddy-002", "nickname": "小明"}]
    )
    agent._ranking_tool = AsyncMock(
        return_value=(
            [{"user_id": "buddy-002", "nickname": "小明", "graph_score": 0.91}],
            [{"user_id": "buddy-002", "nickname": "小明"}],
            {"ranking_backend": "graph"},
        )
    )
    monkeypatch.setattr(recommendations, "get_agent", lambda name: agent)

    payload = _learning_support_payload("studyBuddyRecommendation")
    payload["data"]["candidateUsers"] = [{"userId": "buddy-002"}]
    payload["data"]["interactionContext"] = {"history": [{"userId": "buddy-001"}]}
    with _client() as client:
        response = client.post(
            "/internal/v1/processTutoringInteraction", headers=HEADERS, json=payload
        )

    assert response.json()["code"] == "000000"
    buddies = response.json()["data"]["ext"]["studyBuddyRecommendation"]["buddies"]
    assert [buddy["userId"] for buddy in buddies] == ["buddy-002"]
    agent._fetch_buddy_details.assert_awaited_once_with(["buddy-002"])
    ranking_input = agent._ranking_tool.await_args.args[2]
    assert ranking_input["history_user_ids"] == ["buddy-001"]
    agent.execute.assert_not_awaited()


@pytest.mark.parametrize("interaction", [{"query": 1}, {"history": False}])
def test_learning_support_rejects_invalid_interaction_context(
    interaction: dict[str, Any],
) -> None:
    payload = _learning_support_payload("resourceRecommendation")
    payload["data"]["interactionContext"] = interaction

    with _client() as client:
        response = client.post(
            "/internal/v1/processTutoringInteraction", headers=HEADERS, json=payload
        )

    assert response.json()["code"] == "200002"


def test_learning_support_requires_complete_learning_evidence() -> None:
    payload = _learning_support_payload("resourceRecommendation")
    del payload["data"]["learningEvidence"][0]["occurredAt"]

    with _client() as client:
        response = client.post(
            "/internal/v1/processTutoringInteraction", headers=HEADERS, json=payload
        )

    assert response.json()["code"] == "200001"
