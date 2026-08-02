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
    safety_branch: Optional[str]           # PASS/REJECT/GUIDE
    safety_action: Optional[str]           # 兼容旧调用方，值与 safety_branch 相同
    safety_context: Optional[dict]         # 分类结果与 Skill 输出
    safety_response: Optional[str]         # REJECT/GUIDE 的直接回复
    safety_blocked_response: Optional[str] # 兼容旧 checkpoint

    # ── 本轮重点 agent 评分（decide 之前由 pre-processing 节点写入） ──
    # 短路场景下 decide 不执行，pre_focus 必须被 response_assembler 转发
    pre_focus: list[str]                   # 临时评分结果，decide 后清空
    focus_agents: list[str]                # 本轮最终重点 agent（最多 2 个）
