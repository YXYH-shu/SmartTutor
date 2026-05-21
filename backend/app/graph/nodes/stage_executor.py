"""Stage executor node – runs all agents for the current stage sequentially.

All stages now have ``output_to_user: true`` by design. The last agent's
output becomes the ``final_response``. Internal agents (e.g. cognitive_diagnosis)
run first and pass their results to downstream content-producing agents
(e.g. content_polisher, empathy_generator).

Emotion analysis is handled separately by the ``emotion_preprocess`` node
and is already available in ``ctx["emotion_analyzer"]`` when this node runs.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage

from app.graph.decision_engine import DecisionEngine
from app.graph.state import TutorState
from app.services.agents import get_agent

logger = logging.getLogger(__name__)

_engine: DecisionEngine | None = None


def _get_engine() -> DecisionEngine:
    global _engine
    if _engine is None:
        _engine = DecisionEngine()
    return _engine


async def stage_executor(state: TutorState) -> dict[str, Any]:
    """Execute all agents for the current stage in order."""
    wf_name = state.get("workflow_type") or _get_engine().default_workflow
    stage_id = state.get("current_stage")
    engine = _get_engine()

    logger.info("[stage_executor] workflow=%s stage=%s", wf_name, stage_id)

    from app.services.trace_logger import get_trace_logger
    _trace = get_trace_logger()
    _tid = (state.get("context") or {}).get("_trace_id", "no-trace")
    _trace.debug("[%s] NODE_ENTER stage_executor workflow=%s stage=%s", _tid, wf_name, stage_id)

    # Resolve stage definition
    if stage_id:
        stage_def = engine.get_stage(wf_name, stage_id)
        if not stage_def:
            # stage_id may belong to a different workflow; search all
            logger.warning("[stage_executor] stage '%s' not in '%s', searching all workflows",
                           stage_id, wf_name)
            for wf_key, wf_def in engine.workflows.get("workflows", {}).items():
                for s in wf_def.get("stages", []):
                    if s["id"] == stage_id:
                        wf_name = wf_key
                        stage_def = s
                        break
                if stage_def:
                    break
    else:
        stage_def = engine.get_first_stage(wf_name)

    if not stage_def:
        logger.warning("[stage_executor] no stage found – falling back to first stage of default")
        stage_def = engine.get_first_stage(engine.default_workflow)
        wf_name = engine.default_workflow

    if not stage_def:
        return {"decision": "finish", "requires_user_input": True}

    agent_names: list[str] = stage_def.get("agents", [])
    ctx = {**(state.get("context") or {})}
    last_output: dict[str, Any] | None = None

    # Step queue for SSE streaming – read from ContextVar, never from state
    import json as _json
    from app.graph._stream_ctx import step_queue_var, agent_labels_var

    _step_queue = step_queue_var.get()
    _agent_labels: dict[str, str] = agent_labels_var.get() or {}

    for name in agent_names:
        agent_label = _agent_labels.get(name, name)

        # Emit step event before agent runs
        if _step_queue is not None:
            await _step_queue.put({"type": "step", "label": f"正在运行{agent_label}"})

        logger.info("[stage_executor] running agent: %s", name)
        agent = get_agent(name)

        # Build input from context + state
        input_data: dict[str, Any] = {**ctx}
        input_data.setdefault("user_id", state.get("user_id", ""))
        input_data.setdefault("conversation_id", state.get("conversation_id", ""))

        messages = state.get("messages", [])
        input_data["message_history"] = [
            {"role": getattr(m, "type", "unknown"), "content": getattr(m, "content", "")}
            for m in messages[-10:]
        ]
        # Also provide recent_messages alias for prompt templates that use it
        input_data["recent_messages"] = input_data["message_history"]
        if messages:
            input_data["current_message"] = getattr(messages[-1], "content", "")

        # Pass along specific context keys agents expect
        for key in ("user_profile", "emotion_state", "raw_response", "knowledge_graph", "safety_context"):
            if key in ctx and key not in input_data:
                input_data[key] = ctx[key]

        # Flatten useful fields from prior agent outputs stored in ctx
        # (agents store their full output under their name, but downstream
        #  agents may expect specific keys at the top level)
        if "emotion_analyzer" in ctx and isinstance(ctx["emotion_analyzer"], dict):
            input_data.setdefault("emotion_state", ctx["emotion_analyzer"])
        if "cognitive_diagnosis" in ctx and isinstance(ctx["cognitive_diagnosis"], dict):
            cd = ctx["cognitive_diagnosis"]
            # Pass full diagnosis result for learning_path, resource_recommender, study_buddy
            input_data.setdefault("diagnosis_result", cd)
            # Flatten mastery from knowledge_states into a simple dict for convenience
            mastery_rates = {}
            for ks in cd.get("knowledge_states", []):
                skill = ks.get("skill_id") or ks.get("skill_name", "")
                if skill:
                    mastery_rates[skill] = ks.get("mastery_percent", ks.get("probability_correct", 0))
            input_data.setdefault("mastery_rates", mastery_rates)
            # Pass structured knowledge graph from diagnosis to downstream agents
            kg = cd.get("knowledge_graph")
            if kg and isinstance(kg, dict):
                input_data.setdefault("knowledge_graph", kg)
        # Pass safety context from safety pipeline to downstream agents
        if "safety_context" in ctx and isinstance(ctx["safety_context"], dict):
            input_data["safety_context"] = ctx["safety_context"]
            input_data["transform_tags"] = ctx["safety_context"].get("transform_tags", [])
            input_data["risk_category"] = ctx["safety_context"].get("risk_category")
        # study_buddy template uses 'user_graph' but we store 'knowledge_graph'
        input_data.setdefault("user_graph", input_data.get("knowledge_graph", {}))
        # Flatten prior agent outputs for knowledge_responder
        if "resource_recommender" in ctx and isinstance(ctx["resource_recommender"], dict):
            input_data.setdefault("resource_list", ctx["resource_recommender"])
        if "study_buddy" in ctx and isinstance(ctx["study_buddy"], dict):
            input_data.setdefault("buddy_info", ctx["study_buddy"])
        if "learning_path" in ctx and isinstance(ctx["learning_path"], dict):
            input_data.setdefault("learning_plan", ctx["learning_path"])
        # Populate learning context from user_profile if available
        profile = input_data.get("user_profile") or state.get("user_profile") or {}
        if isinstance(profile, dict):
            input_data.setdefault("current_level", profile.get("current_level", "初级"))
            input_data.setdefault("weak_points", profile.get("weak_points", []))
            input_data.setdefault("learning_style", profile.get("learning_style"))
        # Map current_stage → stage for resource_recommender
        input_data.setdefault("stage", state.get("current_stage", "未指定"))
        # Set target_knowledge from weak points or current topic
        if not input_data.get("target_knowledge"):
            weak = input_data.get("weak_points", [])
            if weak:
                input_data["target_knowledge"] = weak[0]
            else:
                input_data["target_knowledge"] = "未指定"
        # Set topic from current_message for study_buddy
        if not input_data.get("topic"):
            input_data["topic"] = input_data.get("current_message", "未指定")

        # If a previous agent in this stage produced output, pass it as 'content'
        # and 'raw_response' so downstream agents (content_polisher, empathy_generator)
        # can process it regardless of which variable name they expect
        if last_output is not None:
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

        output = result["output"]
        ctx[name] = output
        ctx["_last_agent"] = name
        ctx["_last_output"] = output
        last_output = output

        # Emit thinking event after agent completes
        if _step_queue is not None:
            try:
                thinking_payload = {"agent": agent_label, "agent_output": output}
                await _step_queue.put({
                    "type": "thinking",
                    "content": _json.dumps(thinking_payload, ensure_ascii=False, default=str),
                    "step": name,
                    "label": agent_label,
                })
            except Exception:
                logger.debug("Failed to emit thinking event for %s", name, exc_info=True)

        logger.info("[stage_executor] agent %s done", name)

    # If stage outputs to user, set final_response from the last agent
    updates: dict[str, Any] = {
        "context": ctx,
        "stage_counter": state.get("stage_counter", 0) + 1,
    }

    if stage_def.get("output_to_user", False) and last_output is not None:
        # Try to extract a text response from the output
        response_text = _extract_text(last_output)
        if response_text:
            updates["final_response"] = response_text
            updates["messages"] = [AIMessage(content=response_text)]

    # Check if this was the last stage in the workflow
    next_stage = engine.get_next_stage(wf_name, stage_def["id"])
    if next_stage is None:
        updates["decision"] = "finish"
        updates["requires_user_input"] = True
    else:
        # Move to next stage for the next graph cycle
        updates["current_stage"] = next_stage["id"]
        updates["next_agents"] = next_stage["agents"]
        updates["stage_counter"] = 0

    logger.info("[stage_executor] done – has_response=%s", "final_response" in updates)
    _trace.debug("[%s] NODE_EXIT  stage_executor has_response=%s",
                 _tid, "final_response" in updates)
    return updates


def _extract_text(output: dict[str, Any]) -> str | None:
    """Try to pull a human-readable text from an agent output dict."""
    import json

    # Common string output field names across all agents
    for key in (
        "recommendation_text",
        "topic_analysis",
        "planning_rationale",
        "response_text",
        "transformed_text",
        "empathetic_response",
        "polished_content",
        "diagnosis_summary",
        "rationale",
        "estimated_completion",
        "adaptive_rules",
        "total_estimated_time",
        "contact_suggestion",
    ):
        val = output.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    # Nested string fields (e.g. group_suggestion.formation_strategy)
    for key in ("group_suggestion", "reflection"):
        val = output.get(key)
        if isinstance(val, dict):
            for sub_key in ("formation_strategy", "match_quality", "improvement_suggestion"):
                sub = val.get(sub_key)
                if isinstance(sub, str) and sub.strip():
                    return sub.strip()

    # List fields – join into readable text
    for key in ("weak_points", "recommended_actions", "resources", "buddies"):
        val = output.get(key)
        if isinstance(val, list) and val:
            items = []
            for item in val[:5]:
                if isinstance(item, str):
                    items.append(item)
                elif isinstance(item, dict):
                    name = item.get("title") or item.get("name") or item.get("nickname") or item.get("skill_name")
                    if name:
                        items.append(str(name))
            if items:
                return "\n".join(f"- {i}" for i in items)

    # Fallback: return the whole JSON as formatted text
    return json.dumps(output, ensure_ascii=False, indent=2)
