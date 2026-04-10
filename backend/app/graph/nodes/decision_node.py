"""Decision node – calls the DecisionEngine to route the graph.

Emits one of four decisions:
- continue_stage  → proceed to execute_stage
- switch_stage    → proceed to execute_stage with new stage
- free_composition → proceed to execute_agent (ad-hoc sequence)
- finish          → proceed to assemble_response (end turn)
"""

from __future__ import annotations

import logging
from typing import Any

from app.graph.decision_engine import DecisionEngine
from app.graph.state import TutorState
from app.services.agents import list_agents

logger = logging.getLogger(__name__)

_decision_engine: DecisionEngine | None = None


def _get_engine() -> DecisionEngine:
    global _decision_engine
    if _decision_engine is None:
        _decision_engine = DecisionEngine()
    return _decision_engine


async def decision_node(state: TutorState) -> dict[str, Any]:
    """Invoke the decision engine and return partial state updates."""
    logger.info("[decision_node] entering – workflow=%s stage=%s",
                state.get("workflow_type"), state.get("current_stage"))

    engine = _get_engine()
    agents_meta = list_agents()

    decision = await engine.decide_next_step(dict(state), agents_meta)

    # Strip agents that run as fixed nodes (should never be in agent_sequence)
    _FIXED_AGENTS = {"safety_monitor", "emotion_analyzer"}
    agent_seq = [a for a in decision.get("agent_sequence", []) if a not in _FIXED_AGENTS]

    updates: dict[str, Any] = {
        "decision": decision["decision"],
        "next_agents": agent_seq,
    }

    # Handle workflow/stage transitions
    if decision["decision"] == "switch_stage":
        target_wf = decision.get("target_workflow")
        if not target_wf:
            # Try to infer from target_stage or agent_sequence
            target_stage_id = decision.get("target_stage")
            agent_seq = decision.get("agent_sequence", [])
            # Search all workflows for a matching stage or agent set
            for wf_key, wf_def in engine.workflows.get("workflows", {}).items():
                for s in wf_def.get("stages", []):
                    if (target_stage_id and s["id"] == target_stage_id) or \
                       (set(s.get("agents", [])) & set(agent_seq)):
                        target_wf = wf_key
                        break
                if target_wf:
                    break
            # Final fallback: keep current workflow
            if not target_wf:
                target_wf = state.get("workflow_type") or engine.default_workflow
                logger.warning("[decision_node] switch_stage without target_workflow, inferred=%s", target_wf)
        updates["workflow_type"] = target_wf
        target_stage_id = decision.get("target_stage")
        if target_stage_id:
            stage = engine.get_stage(target_wf, target_stage_id)
        else:
            stage = engine.get_first_stage(target_wf)
        if stage:
            updates["current_stage"] = stage["id"]
            updates["next_agents"] = stage["agents"]
            updates["stage_counter"] = 0
        else:
            logger.error("[decision_node] switch_stage failed: no stage found for wf=%s stage=%s",
                         target_wf, target_stage_id)

    elif decision["decision"] == "continue_stage":
        wf_name = state.get("workflow_type") or engine.default_workflow
        stage_id = state.get("current_stage")
        if stage_id:
            stage = engine.get_stage(wf_name, stage_id)
        else:
            stage = engine.get_first_stage(wf_name)
            if stage:
                updates["current_stage"] = stage["id"]
                updates["workflow_type"] = wf_name
        if stage:
            updates["next_agents"] = stage["agents"]
            updates["stage_counter"] = state.get("stage_counter", 0) + 1

    elif decision["decision"] == "finish":
        updates["requires_user_input"] = True

    logger.info(
        "[decision_node] decision=%s → next_agents=%s",
        decision["decision"],
        updates.get("next_agents", []),
    )
    return updates
