"""Response assembler node – final step before returning to user.

With the restructured workflows, every stage now has ``output_to_user: true``.
Normal educational responses pass through the ``correct_content`` quality gate
before reaching this node, so ``final_response`` should almost always be set.

This node only handles the rare edge case where no response was produced.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage

from app.graph.state import TutorState
from app.services.agents import get_agent

logger = logging.getLogger(__name__)


async def response_assembler(state: TutorState) -> dict[str, Any]:
    """Assemble the final response for the user.

    Normal educational replies are already content-corrected. Falls back to
    empathy_generator only if something went wrong upstream.
    """
    logger.info("[response_assembler] entering")

    from app.services.trace_logger import get_trace_logger
    _trace = get_trace_logger()
    _tid = (state.get("context") or {}).get("_trace_id", "no-trace")
    _trace.debug("[%s] NODE_ENTER response_assembler", _tid)

    # REJECT and GUIDE both finish the current turn with a safety response.
    safety_response = state.get("safety_response") or state.get("safety_blocked_response")
    if safety_response:
        logger.info("[response_assembler] using direct safety response")
        # 短路场景：decide 没跑，pre_focus 仍是临时评分；转发到 focus_agents
        # 让 done 事件能拿到重点 agent。
        pre_focus = list(state.get("pre_focus") or [])
        updates: dict[str, Any] = {
            "final_response": safety_response,
            "messages": [AIMessage(content=safety_response)],
            "requires_user_input": True,
        }
        if pre_focus and not state.get("focus_agents"):
            updates["focus_agents"] = pre_focus[:2]
        return updates

    final = state.get("final_response")

    if not final:
        # Edge case: stage executor didn't produce a response.
        # Use empathy_generator to craft a helpful reply.
        final = await _generate_fallback_response(state)
        if not final:
            final = "我正在思考中，请稍等..."
            logger.warning("[response_assembler] no final_response – using fallback")

    logger.info("[response_assembler] done – response length=%d", len(final))
    _trace.debug("[%s] NODE_EXIT  response_assembler response_length=%d", _tid, len(final))
    return {
        "final_response": final,
        "messages": [AIMessage(content=final)],
        "requires_user_input": True,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _generate_fallback_response(state: TutorState) -> str | None:
    """Generate a meaningful response when no teaching content was produced."""
    messages = state.get("messages", [])
    ctx = state.get("context") or {}
    user_msg = ""
    for msg in reversed(messages):
        if getattr(msg, "type", "") == "human":
            user_msg = getattr(msg, "content", "")
            break
    if not user_msg:
        return None

    from app.graph.nodes.stage_executor import _extract_text

    raw_response = _extract_text(ctx.get("_last_output")) or ""

    try:
        empathy = get_agent("empathy_generator")
        emotion = ctx.get("emotion_analyzer", {})
        result = await empathy.execute(
            input_data={
                "raw_response": raw_response,
                "emotion_state": emotion,
                "scenario": "学生主动提问",
                "user_message": user_msg,
            },
            context={
                "conversation_id": state.get("conversation_id", ""),
                "user_id": state.get("user_id", ""),
            },
        )
        return result["output"].get("empathetic_response")
    except Exception:
        logger.warning("[response_assembler] fallback response generation failed", exc_info=True)
        return raw_response or None
