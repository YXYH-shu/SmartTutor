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

    messages = state.get("messages", [])

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

    logger.info(
        "[emotion_preprocess] done – emotion=%s intensity=%s",
        output.get("emotion"),
        output.get("intensity"),
    )

    return {
        "context": ctx,
        # Append to emotion_history so decision engine can read it
        "emotion_history": [output],
    }
