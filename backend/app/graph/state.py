"""TutorState – the single state object that flows through the LangGraph.

All nodes read from and write to this dict.  Annotated fields define
how concurrent writes are merged (e.g. ``add_messages`` appends rather
than replaces the message list).
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing import TypedDict


class TutorState(TypedDict):
    """State schema for the Tutor Agent graph."""

    # ── Identity ──────────────────────────────────────────────────────
    user_id: str
    conversation_id: str

    # ── Conversation ──────────────────────────────────────────────────
    messages: Annotated[list[BaseMessage], add_messages]

    # ── User snapshot (loaded from DB, cached per turn) ───────────────
    user_profile: Optional[dict]

    # ── Emotion tracking (append-only across turns) ───────────────────
    emotion_history: Annotated[list[dict], operator.add]

    # ── Execution context ─────────────────────────────────────────────
    current_stage: str                    # e.g. "diagnosis", "learning"
    stage_counter: int                    # increments within a stage

    # Transient data shared between agents within one graph run.
    # NOT persisted to the DB – rebuilt from checkpoints.
    context: dict

    # ── Decision model output ─────────────────────────────────────────
    workflow_type: Optional[str]          # e.g. "onboarding", "adaptive_learning"
    decision: Optional[str]               # latest decision verb
    next_agents: list[str]               # ordered agent queue for free-composition

    # ── Output ────────────────────────────────────────────────────────
    final_response: Optional[str]         # text shown to the user
    requires_user_input: bool             # should the graph pause?
    interrupt_reason: Optional[str]       # why it paused (e.g. "need clarification")

    # ── Safety pipeline ──────────────────────────────────────────────
    safety_action: Optional[str]           # SAFE/TRANSFORM/SOFT_BLOCK/HARD_BLOCK/REFERRAL
    safety_context: Optional[dict]         # 安全管线中间结果
    safety_blocked_response: Optional[str] # 拦截时的预设回复
