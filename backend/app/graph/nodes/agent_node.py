"""Agent node – generic executor for a single agent invocation.

Reads agent name from ``state["next_agents"]`` (pops the first entry),
executes it, and stores the result in ``state["context"]``.
"""

from __future__ import annotations

import logging
from typing import Any

from app.graph.state import TutorState
from app.services.agents import get_agent

logger = logging.getLogger(__name__)


async def agent_node(state: TutorState) -> dict[str, Any]:
    """Execute the first agent in the ``next_agents`` queue.

    Returns partial state updates (``context`` enriched, ``next_agents``
    consumed).
    """
    next_agents = list(state.get("next_agents", []))
    ctx = {**(state.get("context") or {})}

    if not next_agents:
        logger.warning("[agent_node] no agents in queue – nothing to execute")
        return {"context": ctx, "next_agents": []}

    agent_name = next_agents.pop(0)
    logger.info("[agent_node] executing agent: %s (queue remaining: %s)", agent_name, next_agents)

    agent = get_agent(agent_name)

    # Build input_data from context + state
    input_data: dict[str, Any] = {**ctx}
    # Attach useful state fields
    input_data.setdefault("user_id", state.get("user_id", ""))
    input_data.setdefault("conversation_id", state.get("conversation_id", ""))

    # Add recent messages as serialisable dicts
    messages = state.get("messages", [])
    input_data["message_history"] = [
        {"role": getattr(m, "type", "unknown"), "content": getattr(m, "content", "")}
        for m in messages[-10:]
    ]
    input_data["recent_messages"] = input_data["message_history"]
    if messages:
        input_data["current_message"] = getattr(messages[-1], "content", "")

    # Flatten context from prior agent outputs
    if "emotion_analyzer" in ctx and isinstance(ctx["emotion_analyzer"], dict):
        input_data.setdefault("emotion_state", ctx["emotion_analyzer"])
    if "cognitive_diagnosis" in ctx and isinstance(ctx["cognitive_diagnosis"], dict):
        cd = ctx["cognitive_diagnosis"]
        input_data.setdefault("knowledge_graph", cd.get("knowledge_graph", {}))
        input_data.setdefault("mastery_rates", cd.get("mastery_rates", {}))
    input_data.setdefault("user_graph", input_data.get("knowledge_graph", {}))
    # Flatten prior agent outputs for knowledge_responder
    if "resource_recommender" in ctx and isinstance(ctx["resource_recommender"], dict):
        input_data.setdefault("resource_list", ctx["resource_recommender"])
    if "study_buddy" in ctx and isinstance(ctx["study_buddy"], dict):
        input_data.setdefault("buddy_info", ctx["study_buddy"])
    if "learning_path" in ctx and isinstance(ctx["learning_path"], dict):
        input_data.setdefault("learning_plan", ctx["learning_path"])
    # Populate learning context from user_profile
    input_data.setdefault("user_profile", state.get("user_profile"))
    profile = input_data.get("user_profile") or state.get("user_profile") or {}
    if isinstance(profile, dict):
        input_data.setdefault("current_level", profile.get("current_level", "初级"))
        input_data.setdefault("weak_points", profile.get("weak_points", []))
        input_data.setdefault("learning_style", profile.get("learning_style"))
    # Map current_stage → stage for agents that use it
    input_data.setdefault("stage", state.get("current_stage", "常规对话"))
    # Set topic from current_message for study_buddy
    if not input_data.get("topic"):
        input_data["topic"] = input_data.get("current_message", "未指定")
    # Pass last agent output for downstream agents
    last_output = ctx.get("_last_output")
    if last_output is not None:
        from app.graph.nodes.stage_executor import _extract_text
        extracted = _extract_text(last_output) or ""
        input_data.setdefault("content", extracted)
        input_data.setdefault("raw_response", extracted)

    result = await agent.execute(
        input_data=input_data,
        context={
            "conversation_id": state.get("conversation_id", ""),
            "user_id": state.get("user_id", ""),
        },
    )

    # Store the agent's output in context under its name
    ctx[agent_name] = result["output"]
    # Also store a convenience key for "latest agent output"
    ctx["_last_agent"] = agent_name
    ctx["_last_output"] = result["output"]

    logger.info("[agent_node] %s done – latency=%dms", agent_name, result.get("latency_ms", 0))
    return {"context": ctx, "next_agents": next_agents}
