"""TutorGraphEngine – high-level interface for the rest of the application.

Usage::

    engine = TutorGraphEngine()
    result = await engine.process_turn(
        user_id="u-123",
        conversation_id="conv-456",
        user_message="我想学Python函数",
    )
    print(result["response"])
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from app.config import settings
from app.database import AsyncSessionLocal
from app.graph.builder import build_tutor_graph
from app.graph.state import TutorState
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.models.user_profile import UserProfile
from sqlalchemy import select

logger = logging.getLogger(__name__)

# Auto-transition mapping: completed_workflow → (next_workflow, first_stage)
_WORKFLOW_TRANSITIONS = {
    "onboarding": ("adaptive_learning", "teaching"),
    "review_assessment": ("adaptive_learning", "teaching"),
}


class TutorGraphEngine:
    """Orchestrates a single tutor graph per conversation turn.

    Handles:
    - Loading user state from DB
    - Initialising the LangGraph checkpointer
    - Invoking the graph
    - Persisting results back to the DB
    """

    def __init__(self) -> None:
        self._checkpointer = self._create_checkpointer()
        self._graph = build_tutor_graph(checkpointer=self._checkpointer)

    # ------------------------------------------------------------------
    # Checkpointer
    # ------------------------------------------------------------------

    @staticmethod
    def _create_checkpointer() -> Any:
        ct = settings.langgraph.checkpoint_type
        if ct == "memory":
            logger.info("Using MemorySaver for checkpoints (dev mode)")
            return MemorySaver()

        # Postgres checkpoint – requires langgraph-checkpoint-postgres
        if ct == "postgres":
            try:
                from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
                # AsyncPostgresSaver needs an async context; for simplicity
                # we wrap it. In production, manage the connection pool.
                # For now, fall back to MemorySaver with a warning.
                logger.warning(
                    "PostgresSaver requires async setup – falling back to MemorySaver. "
                    "Implement async pool in production."
                )
                return MemorySaver()
            except ImportError:
                logger.warning("langgraph-checkpoint-postgres not installed – using MemorySaver")
                return MemorySaver()

        return MemorySaver()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process_turn(
        self,
        user_id: str,
        conversation_id: str,
        user_message: str,
        step_queue: asyncio.Queue | None = None,
    ) -> dict[str, Any]:
        """Process one user turn and return the assistant response.

        Returns
        -------
        dict  {"response": str, "workflow": str, "stage": str}
        """
        logger.info(
            "process_turn – user=%s conv=%s msg='%s'",
            user_id, conversation_id, user_message[:60],
        )

        # Trace: generate trace ID and log TURN_START
        from app.services.trace_logger import get_trace_logger, generate_trace_id
        _trace_id = generate_trace_id()
        get_trace_logger().info(
            "[%s] TURN_START user_id=%s conv=%s msg='%s'",
            _trace_id, user_id, conversation_id, user_message[:200],
        )

        # 1. Load user profile from DB
        user_profile = await self._load_user_profile(user_id)

        # 2. Load conversation metadata (workflow state)
        conv = await self._load_conversation(conversation_id)

        # 3. Determine workflow_type: resume from conversation or assign new
        workflow_type = None
        current_stage = ""
        stage_counter = 0
        if conv:
            if conv.workflow_type:
                workflow_type = conv.workflow_type
            if conv.current_stage:
                current_stage = conv.current_stage
        if (not conv or not conv.workflow_type) and (
            not user_profile or not user_profile.get("current_level")
        ):
            workflow_type = "onboarding"

        # 4. Build state: try to resume from checkpoint, otherwise fresh state
        config = {"configurable": {"thread_id": conversation_id}}
        checkpoint = await self._graph.aget_state(config)
        if checkpoint and checkpoint.values:
            # Resume from checkpoint – only override fields that must change
            state: TutorState = {
                **checkpoint.values,
                "messages": [HumanMessage(content=user_message)],
                "user_profile": user_profile,
                "decision": None,
                "next_agents": checkpoint.values.get("next_agents", []),
                "final_response": None,
                "requires_user_input": False,
                "interrupt_reason": None,
                "safety_action": None,
                "safety_context": None,
                "safety_blocked_response": None,
                "emotion_history": [],  # append-only; checkpoint history preserved by operator.add
            }
            state.setdefault("context", {})["_trace_id"] = _trace_id
            # Only use DB workflow if checkpoint has none (first-turn edge case)
            if workflow_type and not state.get("workflow_type"):
                state["workflow_type"] = workflow_type
                state["current_stage"] = current_stage or ""
                state["stage_counter"] = 0
        else:
            # Fresh state (first turn of conversation)
            state = {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "messages": [HumanMessage(content=user_message)],
                "user_profile": user_profile,
                "emotion_history": [],
                "current_stage": current_stage,
                "stage_counter": stage_counter,
                "context": {"_trace_id": _trace_id},
                "workflow_type": workflow_type,
                "decision": None,
                "next_agents": [],
                "final_response": None,
                "requires_user_input": False,
                "interrupt_reason": None,
                "safety_action": None,
                "safety_context": None,
                "safety_blocked_response": None,
            }

        # 5. Run the graph (stream step progress if queue provided)
        if step_queue is not None:
            result = await self._stream_graph_with_steps(state, config, step_queue)
        else:
            result = await self._graph.ainvoke(state, config=config)

        # 5b. Auto-transition from completed workflows
        if result.get("decision") == "finish":
            completed_wf = result.get("workflow_type") or state.get("workflow_type")
            transition = _WORKFLOW_TRANSITIONS.get(completed_wf)
            if transition:
                result["workflow_type"] = transition[0]
                result["current_stage"] = transition[1]
                logger.info(
                    "Auto-transition: %s complete → %s/%s",
                    completed_wf, transition[0], transition[1],
                )

        # 6. Extract response
        response_text = result.get("final_response") or "我正在思考中，请稍等..."
        workflow = result.get("workflow_type") or state.get("workflow_type") or ""
        stage = result.get("current_stage", "")

        # 6. Persist results (user message already saved by chat_service)
        await self._save_message(conversation_id, "assistant", response_text)
        await self._update_conversation(conversation_id, workflow, stage)

        # 7. Persist emotion history if emotion_analyzer ran
        ctx = result.get("context", {})
        emo = ctx.get("emotion_analyzer")
        if isinstance(emo, dict):
            await self._update_emotion_in_profile(user_id, emo)

        logger.info("process_turn done – workflow=%s stage=%s", workflow, stage)
        get_trace_logger().info("[%s] TURN_END response='%s'", _trace_id, response_text[:500])
        return {
            "response": response_text,
            "workflow": workflow,
            "stage": stage,
        }

    # ------------------------------------------------------------------
    # Graph execution helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_thinking(node_name: str, node_output: dict | None) -> str:
        """Extract full node output as formatted JSON for the thinking panel."""
        import json as _json

        out = node_output or {}
        try:
            if node_name == "safety_check":
                action = out.get("safety_action", "SAFE")
                action_map = {
                    "SAFE": "安全放行",
                    "TRANSFORM": "内容转换",
                    "SOFT_BLOCK": "软性拦截",
                    "HARD_BLOCK": "硬性拦截",
                    "REFERRAL": "转介处理",
                }
                payload: dict[str, Any] = {
                    "action": action_map.get(action, action),
                    "raw_action": action,
                }
                ctx = out.get("safety_context")
                if ctx:
                    payload["safety_context"] = ctx
                blocked = out.get("safety_blocked_response")
                if blocked:
                    payload["blocked_response"] = blocked
                msgs = out.get("messages")
                if msgs:
                    payload["transformed_message"] = msgs[-1].content if hasattr(msgs[-1], "content") else str(msgs[-1])
                return _json.dumps(payload, ensure_ascii=False, indent=2, default=str)

            if node_name == "emotion_preprocess":
                ctx = out.get("context") or {}
                emo = ctx.get("emotion_analyzer")
                if emo:
                    return _json.dumps(emo, ensure_ascii=False, indent=2, default=str)
                return _json.dumps(out, ensure_ascii=False, indent=2, default=str)

            if node_name == "decide":
                payload = {
                    "decision": out.get("decision", "finish"),
                    "next_agents": out.get("next_agents", []),
                }
                for key in ("workflow_type", "current_stage", "stage_counter"):
                    if key in out:
                        payload[key] = out[key]
                return _json.dumps(payload, ensure_ascii=False, indent=2, default=str)

            if node_name in ("execute_stage", "execute_agent"):
                ctx = out.get("context") or {}
                last_agent = ctx.get("_last_agent", "")
                last_output = ctx.get("_last_output") or {}
                payload: dict[str, Any] = {}
                if last_agent:
                    payload["agent"] = last_agent
                if last_output:
                    payload["agent_output"] = last_output
                remaining = out.get("next_agents", [])
                if remaining:
                    payload["remaining_agents"] = remaining
                # Include all accumulated agent outputs from context
                for key in ("cognitive_diagnosis", "learning_path", "resource_recommender",
                            "study_buddy", "knowledge_responder", "content_polisher",
                            "empathy_generator"):
                    if key in ctx and key not in payload.get("agent_output", {}):
                        payload.setdefault("accumulated_outputs", {})[key] = ctx[key]
                return _json.dumps(payload, ensure_ascii=False, indent=2, default=str) if payload else ""

            if node_name == "assemble_response":
                resp = out.get("final_response", "")
                payload = {"final_response_preview": resp[:500] + ("..." if len(resp) > 500 else "")} if resp else {"final_response": ""}
                ctx = out.get("context") or {}
                if ctx.get("safety"):
                    payload["safety_context"] = ctx["safety"]
                if ctx.get("emotion_analyzer"):
                    payload["emotion_state"] = ctx["emotion_analyzer"]
                return _json.dumps(payload, ensure_ascii=False, indent=2, default=str)

        except Exception:
            logger.debug("Failed to extract thinking for %s", node_name, exc_info=True)
        return ""

    async def _stream_graph_with_steps(
        self,
        state: TutorState,
        config: dict,
        step_queue: asyncio.Queue,
    ) -> dict[str, Any]:
        """Run graph via astream(), emitting step labels and thinking content into *step_queue*.

        After each node finishes we push:
        1. The label for the *next* step
        2. A thinking summary of the node that just completed
        """
        STEP_LABEL: dict[str, str] = {
            "safety_check": "安全检查",
            "emotion_preprocess": "情感分析",
            "decide": "智能决策",
            "execute_stage": "教学流程",
            "execute_agent": "智能体运行",
            "assemble_response": "回复组装",
        }

        AGENT_LABELS: dict[str, str] = {
            "cognitive_diagnosis": "认知诊断",
            "learning_path": "路径规划",
            "resource_recommender": "资源推荐",
            "study_buddy": "学习伙伴",
            "knowledge_responder": "知识问答",
            "content_polisher": "内容润色",
            "empathy_generator": "共情回应",
        }

        NEXT_LABEL: dict[str, str] = {
            "safety_check": "正在进行情感分析",
            "emotion_preprocess": "正在进行智能决策",
        }

        # Pass step_queue to stage_executor via ContextVar (not state –
        # asyncio.Queue cannot be serialised by the LangGraph checkpointer).
        from app.graph._stream_ctx import step_queue_var, agent_labels_var

        step_queue_var.set(step_queue)
        agent_labels_var.set(AGENT_LABELS)

        # First step label (before graph starts)
        await step_queue.put({"type": "step", "label": "正在进行安全检查"})

        async for event in self._graph.astream(
            state, config=config, stream_mode="updates"
        ):
            for node_name, node_output in event.items():

                # execute_stage: stage_executor already emitted per-agent events
                if node_name == "execute_stage":
                    await step_queue.put({"type": "step", "label": "正在生成回复"})
                    continue

                # execute_agent: use agent-specific Chinese label
                if node_name == "execute_agent":
                    out_ctx = (node_output or {}).get("context") or {}
                    agent_name = out_ctx.get("_last_agent", "")
                    agent_label = AGENT_LABELS.get(agent_name, agent_name)

                    thinking = self._extract_thinking(node_name, node_output)
                    if thinking:
                        await step_queue.put({
                            "type": "thinking",
                            "content": thinking,
                            "step": agent_name or node_name,
                            "label": agent_label,
                        })

                    remaining = (node_output or {}).get("next_agents", [])
                    if remaining:
                        next_label = AGENT_LABELS.get(remaining[0], remaining[0])
                        await step_queue.put({"type": "step", "label": f"正在运行{next_label}"})
                    else:
                        await step_queue.put({"type": "step", "label": "正在生成回复"})
                    continue

                # All other nodes
                thinking = self._extract_thinking(node_name, node_output)
                if thinking:
                    await step_queue.put({
                        "type": "thinking",
                        "content": thinking,
                        "step": node_name,
                        "label": STEP_LABEL.get(node_name, node_name),
                    })

                # Emit step label for the next node
                if node_name == "decide":
                    decision = (node_output or {}).get("decision", "finish")
                    if decision in ("continue_stage", "switch_stage"):
                        # stage_executor will emit per-agent step events
                        pass
                    elif decision == "free_composition":
                        next_agents = (node_output or {}).get("next_agents", [])
                        if next_agents:
                            agent_lbl = AGENT_LABELS.get(next_agents[0], next_agents[0])
                            await step_queue.put({"type": "step", "label": f"正在运行{agent_lbl}"})
                        else:
                            await step_queue.put({"type": "step", "label": "正在运行智能体"})
                    else:
                        await step_queue.put({"type": "step", "label": "正在生成回复"})
                elif node_name in NEXT_LABEL:
                    await step_queue.put(
                        {"type": "step", "label": NEXT_LABEL[node_name]}
                    )

        # Retrieve final state from checkpointer
        snapshot = await self._graph.aget_state(config)
        return snapshot.values if snapshot and snapshot.values else state

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    async def _load_user_profile(self, user_id: str) -> dict[str, Any] | None:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
            profile = result.scalar_one_or_none()
            if not profile:
                return None
            return {
                "knowledge_graph": profile.knowledge_graph,
                "learning_style": profile.learning_style,
                "current_level": profile.current_level,
                "weak_points": profile.weak_points,
                "preferences": profile.preferences,
                "last_diagnosis": str(profile.last_diagnosis) if profile.last_diagnosis else None,
            }

    async def _load_recent_messages(
        self, conversation_id: str, limit: int = 20
    ) -> list[dict[str, str]]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.desc())
                .limit(limit)
            )
            msgs = list(reversed(result.scalars().all()))
            return [
                {"role": m.role, "content": m.content}
                for m in msgs
            ]

    async def _load_conversation(self, conversation_id: str) -> Conversation | None:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            return result.scalar_one_or_none()

    async def _save_message(
        self, conversation_id: str, role: str, content: str
    ) -> None:
        async with AsyncSessionLocal() as session:
            msg = Message(
                id=str(uuid.uuid4()),
                conversation_id=conversation_id,
                role=role,
                content=content,
            )
            session.add(msg)
            await session.commit()

    async def _update_conversation(
        self, conversation_id: str, workflow_type: str | None, current_stage: str | None = None
    ) -> None:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Conversation).where(Conversation.id == conversation_id)
            )
            conv = result.scalar_one_or_none()
            if conv:
                if workflow_type:
                    conv.workflow_type = workflow_type
                # Persist current_stage for workflow continuity
                if current_stage:
                    conv.current_stage = current_stage
                session.add(conv)
                await session.commit()

    async def _update_emotion_in_profile(
        self, user_id: str, emotion: dict
    ) -> None:
        """Store the latest emotion reading in the user profile preferences."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
            profile = result.scalar_one_or_none()
            if profile:
                prefs = profile.preferences or {}
                prefs["last_emotion"] = emotion
                profile.preferences = prefs
                session.add(profile)
                await session.commit()
