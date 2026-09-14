"""Stage handlers for processTutoringInteraction.

本文件实现三个 processingStage（规范 5.2 允许提供方在不改变既有语义
的前提下增加阶段）：

- emotionAnalysis  – 情感分析，输出对象严格按规范 emotion 定义，
  后续组装标准 postResponse 阶段时可直接内嵌复用。
- empathyResponse – 共情回复，不在规范最低输出内，纯扩展能力。
- learningSupport – 资源推荐和学伴推荐，复用规范定义的学情支持阶段。

handler 只做三件事：标准字段 → agent 输入映射、调 agent、agent 输出 →
标准字段映射 + trace。模型超时/失败按规范 5.5 转 degraded 降级成功，
不虚构情绪或共情文本。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from app.api.internal.schemas import (
    DegradedInfo,
    EmotionResult,
    EmpathyResult,
    Trace,
)
from app.api.internal.recommendations import RecommendationError, handle_learning_support
from app.services.agents import get_agent

logger = logging.getLogger(__name__)


class StageError(Exception):
    """阶段内参数校验失败，code 使用公共返回码（200001/200002）."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _trace(agent_version: str) -> dict[str, Any]:
    return Trace(
        trace_id=uuid.uuid4().hex,
        capability_version=agent_version,
        processed_at=datetime.now(timezone.utc).isoformat(),
    ).model_dump(by_alias=True)


def _degraded(reason: str, trace: dict[str, Any]) -> dict[str, Any]:
    info = DegradedInfo(degrade_reason=reason).model_dump(by_alias=True)
    return {"degraded": True, **info, "trace": trace}


_HUMAN_ROLES = {"human", "user", "student", "学生"}
_AI_ROLES = {"ai", "assistant", "teacher", "bot", "老师"}


def _normalize_history(raw: Any, limit: int = 10) -> list[dict[str, str]]:
    """容忍多种 history 写法，统一为 agent 需要的 {role: human|ai, content}."""
    if not isinstance(raw, list):
        return []
    history: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        content = item.get("content") or item.get("text")
        if not content:
            continue
        role = str(item.get("role", "")).lower()
        normalized = "human" if role in _HUMAN_ROLES else "ai"
        history.append({"role": normalized, "content": str(content)})
    return history[-limit:]


async def handle_emotion_analysis(data: dict[str, Any], user_id: str) -> dict[str, Any]:
    scenario_code = data.get("scenarioCode")
    if not scenario_code:
        raise StageError("200001", "data.scenarioCode 缺失")
    interaction = data.get("interactionContext")
    if not isinstance(interaction, dict) or not interaction.get("query"):
        raise StageError("200001", "data.interactionContext.query 缺失")

    history = _normalize_history(interaction.get("history"))
    draft = interaction.get("draftAnswer")
    if draft:
        history.append({"role": "ai", "content": str(draft)})

    agent = get_agent("emotion_analyzer")
    try:
        result = await agent.execute(
            input_data={
                "message_history": history,
                "current_message": str(interaction["query"]),
            },
        )
        output = result["output"]
    except Exception as exc:
        logger.warning(
            "emotionAnalysis degraded – agent failure: %s: %s",
            type(exc).__name__, exc,
        )
        return _degraded(f"情感分析模型调用失败: {type(exc).__name__}", _trace(agent.version))

    emotion = str(output.get("emotion") or "").lower()
    if emotion not in {"positive", "negative", "neutral"}:
        return _degraded("情感分析输出解析失败，无法给出情绪结论", _trace(agent.version))

    return {
        "emotion": EmotionResult(
            dominant_emotion=emotion,
            reason=str(output.get("reason") or ""),
            vad=None,
            vad_note="当前模型为三分类专精模型，无VAD输出，按规范返回null（信息不足，不虚构）",
        ).model_dump(by_alias=True),
        "trace": _trace(agent.version),
    }


def _user_context_profile(user_context: Any) -> dict[str, Any]:
    """外部 userContext → 画像兜底；库内画像存在时由 enrich_input 覆盖."""
    if not isinstance(user_context, dict):
        return {}
    keys = ("stage", "grade", "subject", "learnerStateSummary")
    return {k: user_context[k] for k in keys if user_context.get(k)}


async def handle_empathy_response(data: dict[str, Any], user_id: str) -> dict[str, Any]:
    scenario_code = data.get("scenarioCode")
    if not scenario_code:
        raise StageError("200001", "data.scenarioCode 缺失")
    interaction = data.get("interactionContext")
    if not isinstance(interaction, dict) or not interaction.get("draftAnswer"):
        raise StageError("200001", "data.interactionContext.draftAnswer 缺失")

    scenario = str(scenario_code)
    query = interaction.get("query")
    if query:
        scenario = f"{scenario}；学生问题：{query}"

    emotion_state = data.get("emotion")
    if not isinstance(emotion_state, dict):
        emotion_state = {}

    agent = get_agent("empathy_generator")
    try:
        result = await agent.execute(
            input_data={
                "raw_response": str(interaction["draftAnswer"]),
                "emotion_state": emotion_state,
                "user_profile": _user_context_profile(data.get("userContext")),
                "scenario": scenario,
                "user_id": user_id,
            },
        )
        output = result["output"]
    except Exception as exc:
        logger.warning(
            "empathyResponse degraded – agent failure: %s: %s",
            type(exc).__name__, exc,
        )
        return _degraded(f"共情生成模型调用失败: {type(exc).__name__}", _trace(agent.version))

    empathetic = str(output.get("empathetic_response") or "")
    if not empathetic:
        return _degraded("共情生成输出解析失败，不返回虚构文本", _trace(agent.version))

    return {
        "empathy": EmpathyResult(
            empathetic_response=empathetic,
            psychological_techniques=[
                str(t) for t in (output.get("psychological_techniques") or [])
            ],
            teacher_persona=str(output.get("teacher_persona") or ""),
        ).model_dump(by_alias=True),
        "trace": _trace(agent.version),
    }


async def handle_learning_support_stage(data: dict[str, Any], user_id: str) -> dict[str, Any]:
    try:
        return await handle_learning_support(data, user_id)
    except RecommendationError as exc:
        raise StageError(exc.code, exc.message) from exc


StageHandler = Callable[[dict[str, Any], str], Awaitable[dict[str, Any]]]

STAGE_HANDLERS: dict[str, StageHandler] = {
    "emotionAnalysis": handle_emotion_analysis,
    "empathyResponse": handle_empathy_response,
    "learningSupport": handle_learning_support_stage,
}
