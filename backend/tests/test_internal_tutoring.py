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
