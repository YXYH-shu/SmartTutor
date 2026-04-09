"""Safety gate node – first node in every graph run.

Inspects the latest user message through the safety_monitor agent.
If the content is unsafe, the transformed text replaces the original
in the state and a warning is logged.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from app.graph.state import TutorState
from app.services.agents import get_agent

logger = logging.getLogger(__name__)


async def safety_gate(state: TutorState) -> dict[str, Any]:
    """Run safety check on the latest user message.

    Returns partial state updates to be merged by LangGraph.
    """
    logger.info("[safety_gate] entering – conversation=%s", state.get("conversation_id"))

    messages = state.get("messages", [])
    if not messages:
        logger.info("[safety_gate] no messages – skipping")
        return {"context": {**(state.get("context") or {})}}

    # Find the latest HumanMessage
    last_user_msg = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_user_msg = msg.content
            break

    if not last_user_msg:
        return {"context": {**(state.get("context") or {})}}

    agent = get_agent("safety_monitor")
    result = await agent.execute(
        input_data={"raw_text": last_user_msg, "user_age": state.get("user_profile", {}).get("age", "未知")},
        context={
            "conversation_id": state.get("conversation_id", ""),
            "user_id": state.get("user_id", ""),
        },
    )

    output = result["output"]
    ctx = {**(state.get("context") or {})}
    ctx["safety"] = output

    # If unsafe, replace the user message with the transformed version
    updates: dict[str, Any] = {"context": ctx}
    if not output.get("is_safe", True):
        logger.warning(
            "[safety_gate] unsafe content detected (risk=%s): %s",
            output.get("risk_level"),
            output.get("education_note", "")[:100],
        )
        # Replace the last human message content
        updates["messages"] = [HumanMessage(content=output.get("transformed_text", last_user_msg))]

    logger.info("[safety_gate] done – is_safe=%s", output.get("is_safe", True))
    return updates
