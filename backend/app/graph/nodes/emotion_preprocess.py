"""Emotion preprocess node – runs emotion_analyzer on every turn.

This node is placed between safety_check and decide in the graph so that
emotion data is always available for the decision engine and downstream
agents.  It does NOT go through the decision model.
"""

from __future__ import annotations

import logging
from typing import Any

from app.graph.state import TutorState
from app.services.agents import get_agent

logger = logging.getLogger(__name__)


async def emotion_preprocess(state: TutorState) -> dict[str, Any]:
    """Always run emotion analysis before the decision node.

    Returns partial state updates:
    - ``context["emotion_analyzer"]`` – full emotion analysis output
    - ``emotion_history`` – appended entry for decision engine use
    """
    logger.info("[emotion_preprocess] entering")

    from app.services.trace_logger import get_trace_logger
    _trace = get_trace_logger()
    _tid = (state.get("context") or {}).get("_trace_id", "no-trace")
    _trace.debug("[%s] NODE_ENTER emotion_preprocess", _tid)

    messages = state.get("messages", [])

    # On a GUIDE-resolved turn the checkpoint history still contains the
    # original risky query; only the safety-replaced safe message may reach
    # the emotion LLM (mirrors stage_executor._messages_for_stage).
    safety_context = (state.get("context") or {}).get("safety_context") or {}
    if safety_context.get("resolved_from_guide") is True:
        safe_messages = []
        for msg in reversed(messages):
            if getattr(msg, "type", "") == "human":
                safe_messages = [msg]
                break
        messages = safe_messages

    # Build message history (last 10 messages)
    message_history = [
        {"role": getattr(m, "type", "unknown"), "content": getattr(m, "content", "")}
        for m in messages[-10:]
    ]

    # Extract the latest human message as current_message
    current_message = ""
    for msg in reversed(messages):
        if getattr(msg, "type", "") == "human":
            current_message = getattr(msg, "content", "")
            break

    if not current_message:
        logger.info("[emotion_preprocess] no user message – skipping")
        ctx = {**(state.get("context") or {})}
        return {"context": ctx}

    # Run emotion_analyzer agent
    agent = get_agent("emotion_analyzer")
    result = await agent.execute(
        input_data={
            "message_history": message_history,
            "current_message": current_message,
        },
        context={
            "conversation_id": state.get("conversation_id", ""),
            "user_id": state.get("user_id", ""),
        },
    )

    output = result["output"]
    ctx = {**(state.get("context") or {})}
    ctx["emotion_analyzer"] = output

    # 情感模型 v2 为三分类（positive/negative/neutral），不再有 intensity 字段。
    # 强负面情绪标记为重点关注；其他不做 pre_focus 提升（保持决策权重平衡）。
    polarity = str(output.get("emotion") or "").lower()
    pre_focus: list[str] = []
    if polarity == "negative":
        pre_focus = ["emotion_analyzer"]

    logger.info(
        "[emotion_preprocess] done – polarity=%s reason=%s",
        polarity,
        (output.get("reason") or "")[:80],
    )

    _trace.debug("[%s] NODE_EXIT  emotion_preprocess polarity=%s",
                 _tid, polarity)

    updates: dict[str, Any] = {
        "context": ctx,
        # Append to emotion_history so decision engine can read it
        "emotion_history": [output],
    }
    if pre_focus:
        # 与 safety 写入的 pre_focus 合并（list 默认覆盖；safety 早于此节点，
        # 但 emotion 只在强负面时追加，不会覆盖 safety）
        existing = list(state.get("pre_focus") or [])
        for a in pre_focus:
            if a not in existing:
                existing.append(a)
        updates["pre_focus"] = existing
    return updates
