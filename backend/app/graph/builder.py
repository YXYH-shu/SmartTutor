"""Graph builder – wires all nodes into a LangGraph StateGraph.

```
  START → safety_check → emotion_preprocess → decide ─┬─ continue_stage → execute_stage → correct_content → assemble_response → END
                                                        ├─ switch_stage   → execute_stage → correct_content → assemble_response → END
                                                        ├─ free_composition → execute_agent ↻ (loops until queue empty)
                                                        │                           ↓ correct_content → assemble_response → END
                                                        └─ finish → correct_content → assemble_response → END

  correct_content ── REGENERATE → regenerate_content → correct_content
                  └─ PASS/PATCH ─────────────────────→ assemble_response
```

The ``emotion_preprocess`` node always runs ``emotion_analyzer`` before the
decision node so that emotion data is available for routing and downstream
agents without going through the decision model.  On a GUIDE-resolved turn
the flow continues straight from ``emotion_preprocess`` to ``execute_stage``
with the deterministic queue set by the safety gate (no decision node).

The ``execute_agent`` node loops back to itself while there are agents
remaining in ``next_agents``; once the queue is empty it forwards to the
final ``correct_content`` quality gate.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from langgraph.graph import END, StateGraph

from app.graph.state import TutorState

logger = logging.getLogger(__name__)


def _resolved_from_guide(state: TutorState) -> bool:
    """True when this turn is a confirmed GUIDE safe-learning choice."""
    safety_context = (
        (state.get("context") or {}).get("safety_context")
        or state.get("safety_context")
        or {}
    )
    return safety_context.get("resolved_from_guide") is True


def _route_after_safety(state: TutorState) -> str:
    """Only PASS continues; REJECT and GUIDE return a direct response."""
    branch = state.get("safety_branch") or state.get("safety_action")
    if branch in ("REJECT", "GUIDE"):
        return "assemble_response"
    return "emotion_preprocess"


def _route_after_emotion(state: TutorState) -> str:
    """A GUIDE-resolved turn goes straight to the deterministic teaching
    queue; the risky original conversation never reaches the decision LLM."""
    if _resolved_from_guide(state):
        return "execute_stage"
    return "decide"


def _route_after_decide(state: TutorState) -> str:
    """Conditional edge after the decision node."""
    decision = state.get("decision", "finish")
    if decision in ("continue_stage", "switch_stage"):
        return "execute_stage"
    if decision == "free_composition":
        return "execute_agent"
    # finish or anything else still passes through the final quality gate.
    return "correct_content"


def _route_after_agent(state: TutorState) -> str:
    """After executing one agent, check if more agents remain."""
    if state.get("next_agents"):
        return "execute_agent"  # loop
    return "correct_content"


def _route_after_correction(state: TutorState) -> str:
    """Regenerate once when the final quality gate rejects the answer."""
    ctx = state.get("context") or {}
    audit = ctx.get("content_corrector") or {}
    if audit.get("action") == "REGENERATE":
        return "regenerate_content"
    return "assemble_response"


def build_tutor_graph(checkpointer: Any | None = None) -> StateGraph:
    """Build and compile the tutor agent graph.

    Parameters
    ----------
    checkpointer
        A LangGraph checkpointer instance (``MemorySaver`` or
        ``AsyncPostgresSaver``).  Pass ``None`` for no persistence.

    Returns
    -------
    CompiledGraph – call ``.ainvoke(state)`` or ``.astream(state)``.
    """
    from app.graph.nodes.safety_gate import safety_gate
    from app.graph.nodes.emotion_preprocess import emotion_preprocess
    from app.graph.nodes.decision_node import decision_node
    from app.graph.nodes.agent_node import agent_node
    from app.graph.nodes.stage_executor import stage_executor
    from app.graph.nodes.content_correction import content_correction
    from app.graph.nodes.content_regeneration import content_regeneration
    from app.graph.nodes.response_assembler import response_assembler

    graph = StateGraph(TutorState)

    # ── Nodes ────────────────────────────────────────────────────────
    graph.add_node("safety_check", safety_gate)
    graph.add_node("emotion_preprocess", emotion_preprocess)
    graph.add_node("decide", decision_node)
    graph.add_node("execute_stage", stage_executor)
    graph.add_node("execute_agent", agent_node)
    graph.add_node("correct_content", content_correction)
    graph.add_node("regenerate_content", content_regeneration)
    graph.add_node("assemble_response", response_assembler)

    # ── Edges ────────────────────────────────────────────────────────
    graph.set_entry_point("safety_check")
    graph.add_conditional_edges(
        "safety_check",
        _route_after_safety,
        {
            "emotion_preprocess": "emotion_preprocess",
            "assemble_response": "assemble_response",
        },
    )
    graph.add_conditional_edges(
        "emotion_preprocess",
        _route_after_emotion,
        {
            "decide": "decide",
            "execute_stage": "execute_stage",
        },
    )

    graph.add_conditional_edges(
        "decide",
        _route_after_decide,
        {
            "execute_stage": "execute_stage",
            "execute_agent": "execute_agent",
            "correct_content": "correct_content",
        },
    )

    graph.add_edge("execute_stage", "correct_content")

    # execute_agent loops until next_agents is empty
    graph.add_conditional_edges(
        "execute_agent",
        _route_after_agent,
        {
            "execute_agent": "execute_agent",
            "correct_content": "correct_content",
        },
    )

    graph.add_conditional_edges(
        "correct_content",
        _route_after_correction,
        {
            "regenerate_content": "regenerate_content",
            "assemble_response": "assemble_response",
        },
    )
    graph.add_edge("regenerate_content", "correct_content")
    graph.add_edge("assemble_response", END)

    compiled = graph.compile(checkpointer=checkpointer)
    logger.info("Tutor graph compiled (checkpointer=%s)", type(checkpointer).__name__)
    return compiled
