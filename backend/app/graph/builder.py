"""Graph builder – wires all nodes into a LangGraph StateGraph.

```
  START → safety_check → emotion_preprocess → decide ─┬─ continue_stage → execute_stage → assemble_response → END
                                                        ├─ switch_stage   → execute_stage → assemble_response → END
                                                        ├─ free_composition → execute_agent ↻ (loops until queue empty)
                                                        │                                        ↓ assemble_response → END
                                                        └─ finish → assemble_response → END
```

The ``emotion_preprocess`` node always runs ``emotion_analyzer`` before the
decision node so that emotion data is available for routing and downstream
agents without going through the decision model.

The ``execute_agent`` node loops back to itself while there are agents
remaining in ``next_agents``; once the queue is empty it forwards to
``assemble_response``.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from langgraph.graph import END, StateGraph

from app.graph.state import TutorState

logger = logging.getLogger(__name__)


def _route_after_decide(state: TutorState) -> str:
    """Conditional edge after the decision node."""
    decision = state.get("decision", "finish")
    if decision in ("continue_stage", "switch_stage"):
        return "execute_stage"
    if decision == "free_composition":
        return "execute_agent"
    # finish or anything else
    return "assemble_response"


def _route_after_agent(state: TutorState) -> str:
    """After executing one agent, check if more agents remain."""
    if state.get("next_agents"):
        return "execute_agent"  # loop
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
    from app.graph.nodes.response_assembler import response_assembler

    graph = StateGraph(TutorState)

    # ── Nodes ────────────────────────────────────────────────────────
    graph.add_node("safety_check", safety_gate)
    graph.add_node("emotion_preprocess", emotion_preprocess)
    graph.add_node("decide", decision_node)
    graph.add_node("execute_stage", stage_executor)
    graph.add_node("execute_agent", agent_node)
    graph.add_node("assemble_response", response_assembler)

    # ── Edges ────────────────────────────────────────────────────────
    graph.set_entry_point("safety_check")
    graph.add_edge("safety_check", "emotion_preprocess")
    graph.add_edge("emotion_preprocess", "decide")

    graph.add_conditional_edges(
        "decide",
        _route_after_decide,
        {
            "execute_stage": "execute_stage",
            "execute_agent": "execute_agent",
            "assemble_response": "assemble_response",
        },
    )

    graph.add_edge("execute_stage", "assemble_response")

    # execute_agent loops until next_agents is empty
    graph.add_conditional_edges(
        "execute_agent",
        _route_after_agent,
        {
            "execute_agent": "execute_agent",
            "assemble_response": "assemble_response",
        },
    )

    graph.add_edge("assemble_response", END)

    compiled = graph.compile(checkpointer=checkpointer)
    logger.info("Tutor graph compiled (checkpointer=%s)", type(checkpointer).__name__)
    return compiled
