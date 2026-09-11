"""Pydantic models for the /internal/v1 processTutoringInteraction contract.

Field naming follows the 课题五 standard: JSON keys use lower camelCase.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


def to_camel(snake: str) -> str:
    head, *rest = snake.split("_")
    return head + "".join(part.title() for part in rest)


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Trace(CamelModel):
    """链路定位与能力版本识别（规范 5.4 trace 最低字段）."""

    trace_id: str
    capability_version: str
    processed_at: str


class EmotionResult(CamelModel):
    """情感分析结果（规范 5.4 emotion 最低字段 + 扩展 reason/vadNote）."""

    dominant_emotion: str
    reason: str = ""
    # 当前模型为三分类专精模型，无 VAD 输出；按规范用 null 表达，不虚构数值。
    vad: dict[str, Any] | None = None
    vad_note: str = ""

    @field_validator("dominant_emotion")
    @classmethod
    def _check_emotion(cls, v: str) -> str:
        allowed = {"positive", "negative", "neutral"}
        if v not in allowed:
            raise ValueError(f"dominant_emotion 必须是 {sorted(allowed)} 之一")
        return v


class EmpathyResult(CamelModel):
    """共情回复结果（扩展阶段 empathyResponse 的扩展结果）."""

    empathetic_response: str
    psychological_techniques: list[str] = []
    teacher_persona: str = ""


class DegradedInfo(CamelModel):
    """降级标记（规范 5.5：degraded/degradeReason/availableResults）."""

    degrade_reason: str
    available_results: list[str] = []
