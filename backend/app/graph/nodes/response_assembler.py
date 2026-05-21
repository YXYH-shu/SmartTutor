"""Response assembler node – final step before returning to user.

With the restructured workflows, every stage now has ``output_to_user: true``
and ends with a content-producing agent (content_polisher or empathy_generator).
So ``final_response`` should almost always be set by the stage executor.

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

    Since all stages now produce output, final_response is expected to exist.
    Falls back to empathy_generator only if something went wrong upstream.
    """
    logger.info("[response_assembler] entering")

    from app.services.trace_logger import get_trace_logger
    _trace = get_trace_logger()
    _tid = (state.get("context") or {}).get("_trace_id", "no-trace")
    _trace.debug("[%s] NODE_ENTER response_assembler", _tid)

    # Check for safety-blocked response first
    blocked = state.get("safety_blocked_response")
    if blocked:
        logger.info("[response_assembler] using safety-blocked response")
        return {
            "final_response": blocked,
            "messages": [AIMessage(content=blocked)],
            "requires_user_input": True,
        }

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

    try:
        empathy = get_agent("empathy_generator")
        emotion = ctx.get("emotion_analyzer", {})
        result = await empathy.execute(
            input_data={
                "raw_response": "",
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
        return None
