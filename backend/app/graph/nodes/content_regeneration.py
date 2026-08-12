"""Return a rejected answer to the original content-generating agent once."""

from __future__ import annotations

import logging
from typing import Any

from app.graph.state import TutorState
from app.services.agents import get_agent

logger = logging.getLogger(__name__)


def _latest_user_message(state: TutorState) -> str:
    for message in reversed(state.get("messages", [])):
        if getattr(message, "type", "") == "human":
            content = getattr(message, "content", "")
            return content if isinstance(content, str) else ""
    return ""


async def content_regeneration(state: TutorState) -> dict[str, Any]:
    """Ask knowledge_responder to rewrite using the gate's issue list."""
    ctx = {**(state.get("context") or {})}
    audit = ctx.get("content_corrector") or {}
    issues = audit.get("issues") or ["回答未通过教育完整性验收"]
    previous_response = state.get("final_response") or ""

    input_data: dict[str, Any] = {
        **ctx,
        "current_message": _latest_user_message(state),
        "stage": state.get("current_stage", "teaching"),
        "previous_response": previous_response,
        "correction_issues": issues,
        "regeneration_required": True,
        "user_profile": state.get("user_profile") or {},
    }
    if isinstance(ctx.get("cognitive_diagnosis"), dict):
        input_data["diagnosis_result"] = ctx["cognitive_diagnosis"]
    if isinstance(ctx.get("resource_recommender"), dict):
        input_data["resource_list"] = ctx["resource_recommender"]
    if isinstance(ctx.get("learning_path"), dict):
        input_data["learning_plan"] = ctx["learning_path"]
    if isinstance(ctx.get("study_buddy"), dict):
        input_data["buddy_info"] = ctx["study_buddy"]
    if isinstance(ctx.get("safety_context"), dict):
        input_data["safety_context"] = ctx["safety_context"]

    try:
        result = await get_agent("knowledge_responder").execute(
            input_data=input_data,
            context={
                "conversation_id": state.get("conversation_id", ""),
                "user_id": state.get("user_id", ""),
                "turn_id": ctx.get("turn_id"),
            },
        )
        output = result.get("output")
        if not isinstance(output, dict):
            raise ValueError("knowledge_responder returned a non-object output")
        from app.graph.nodes.stage_executor import _extract_text

        regenerated = _extract_text(output)
        if not regenerated:
            raise ValueError("knowledge_responder returned no response text")
    except Exception as exc:
        logger.warning("[content_regeneration] failed; keeping previous response: %s", exc)
        regenerated = previous_response
        output = {"response_text": previous_response, "error": type(exc).__name__}

    ctx["_content_regeneration_count"] = int(ctx.get("_content_regeneration_count") or 0) + 1
    ctx["knowledge_responder_regeneration"] = {
        **output,
        "correction_issues": issues,
    }
    ctx["_last_agent"] = "knowledge_responder"
    ctx["_last_output"] = ctx["knowledge_responder_regeneration"]
    return {"final_response": regenerated, "context": ctx}
