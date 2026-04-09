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
        if not user_profile or not user_profile.get("current_level"):
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
                "emotion_history": [],  # append-only; checkpoint history preserved by operator.add
            }
            # Allow DB-driven overrides if workflow was explicitly changed externally
            if workflow_type and workflow_type != state.get("workflow_type"):
                state["workflow_type"] = workflow_type
                state["current_stage"] = current_stage
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
                "context": {},
                "workflow_type": workflow_type,
                "decision": None,
                "next_agents": [],
                "final_response": None,
                "requires_user_input": False,
                "interrupt_reason": None,
            }

        # 5. Run the graph
        result = await self._graph.ainvoke(state, config=config)

        # 5. Extract response
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
        return {
            "response": response_text,
            "workflow": workflow,
            "stage": stage,
        }

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
