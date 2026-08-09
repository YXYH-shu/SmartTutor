"""Safety gate node – first node in every graph run.

Implements a 5-stage safety pipeline:
1. Risk perception
2. Intent recognition
3. Value assessment
4. Educational guidance (if TRANSFORM)
5. Problem transformation (if TRANSFORM)

Results are stored in state for downstream routing and agent context.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage

from app.graph.state import TutorState
from app.services.safety_pipeline import SafetyPipeline

logger = logging.getLogger(__name__)

_pipeline: SafetyPipeline | None = None
_KT_STUDENT_ID_RE = re.compile(r"(?:学生|student)\s*#?\s*(\d+)", re.IGNORECASE)


def _extract_kt_student_id(message: str) -> str | None:
    match = _KT_STUDENT_ID_RE.search(message)
    return match.group(1) if match else None


def _get_pipeline() -> SafetyPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = SafetyPipeline()
    return _pipeline


async def safety_gate(state: TutorState) -> dict[str, Any]:
    """Run the 5-stage safety pipeline on the latest user message."""
    logger.info("[safety_gate] entering – conversation=%s", state.get("conversation_id"))

    from app.services.trace_logger import get_trace_logger
    _trace = get_trace_logger()
    _tid = (state.get("context") or {}).get("_trace_id", "no-trace")
    _trace.debug("[%s] NODE_ENTER safety_gate", _tid)

    messages = state.get("messages", [])
    if not messages:
        logger.info("[safety_gate] no messages – skipping")
        return {
            "safety_action": "SAFE",
            "context": {**(state.get("context") or {})},
        }

    # Find the latest HumanMessage
    last_user_msg = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_user_msg = msg.content
            break

    if not last_user_msg:
        return {
            "safety_action": "SAFE",
            "context": {**(state.get("context") or {})},
        }

    # Get student grade from user profile
    profile = state.get("user_profile") or {}
    student_grade = profile.get("grade_level") or profile.get("current_level") or "未知"

    # Build conversation context string
    context_lines = []
    for msg in messages[:-1]:  # exclude current message
        role = "user" if getattr(msg, "type", "") == "human" else "assistant"
        content = getattr(msg, "content", "")
        if content:
            context_lines.append(f"{role}: {content}")
    conversation_context = "\n".join(context_lines[-6:])  # last 6 messages

    shared_context = {**(state.get("context") or {})}
    kt_student_id = _extract_kt_student_id(str(last_user_msg))
    if kt_student_id:
        shared_context["kt_student_id"] = kt_student_id

    try:
        pipeline = _get_pipeline()
        result = await pipeline.execute(
            query=last_user_msg,
            student_grade=student_grade,
            conversation_context=conversation_context,
        )
    except Exception:
        logger.error("[safety_gate] pipeline failed – defaulting to SAFE", exc_info=True)
        return {
            "safety_action": "SAFE",
            "context": shared_context,
        }

    updates: dict[str, Any] = {
        "safety_action": result.action,
        "safety_context": result.safety_context,
    }

    ctx = shared_context
    ctx["safety"] = result.safety_context or {}

    if result.action == "SAFE":
        logger.info("[safety_gate] content is safe")
        updates["context"] = ctx

    elif result.action == "TRANSFORM":
        logger.info(
            "[safety_gate] transforming query (risk=%s)",
            result.safety_context.get("risk_category") if result.safety_context else None,
        )
        # Replace the user message with the transformed version
        updates["messages"] = [HumanMessage(content=result.transformed_query)]
        updates["context"] = ctx
        # 触发了转换 → 本轮重点标记 safety_monitor
        updates["pre_focus"] = ["safety_monitor"]

    elif result.action in ("SOFT_BLOCK", "HARD_BLOCK", "REFERRAL"):
        logger.warning(
            "[safety_gate] blocking: action=%s",
            result.action,
        )
        updates["safety_blocked_response"] = result.blocked_response
        updates["context"] = ctx
        # 拦截场景 → 本轮重点标记 safety_monitor
        updates["pre_focus"] = ["safety_monitor"]

    _trace.debug("[%s] NODE_EXIT  safety_gate safety_action=%s", _tid, result.action)
    return updates
