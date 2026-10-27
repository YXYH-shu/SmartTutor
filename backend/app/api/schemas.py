"""Centralised API request/response schemas.

Avoids circular imports – every router imports from this single file.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field


# ── Auth ──────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: "UserResponse"


class RefreshRequest(BaseModel):
    refresh_token: str


# ── User ──────────────────────────────────────────────────────────────

class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ProfileResponse(BaseModel):
    id: str
    user_id: str
    knowledge_graph: dict[str, Any]
    learning_style: Optional[str]
    current_level: str
    weak_points: list[Any]
    preferences: dict[str, Any]
    last_diagnosis: Optional[datetime]
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProfileUpdateRequest(BaseModel):
    learning_style: Optional[str] = None
    current_level: Optional[str] = None
    preferences: Optional[dict[str, Any]] = None


class UserStatsResponse(BaseModel):
    total_conversations: int
    total_messages: int
    knowledge_points_count: int
    streak_days: int


# ── Conversation ──────────────────────────────────────────────────────

class ConversationCreateRequest(BaseModel):
    title: Optional[str] = Field(default="新对话", max_length=255)
    workflow_type: Optional[str] = None


class ConversationResponse(BaseModel):
    id: str
    user_id: str
    title: Optional[str]
    workflow_type: Optional[str]
    created_at: datetime
    updated_at: datetime
    ended_at: Optional[datetime] = None
    last_message: Optional[str] = None  # preview
    knowledge_points: Optional[list["KnowledgeNodeSummary"]] = None
    highlight_agent: Optional[str] = None

    model_config = {"from_attributes": True}


class ConversationDetailResponse(ConversationResponse):
    messages: list["MessageResponse"] = []


class TitleUpdateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)


# ── Message / Chat ────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    agent_type: Optional[str]
    emotion_state: Optional[dict[str, Any]]
    metadata: Optional[dict[str, Any]]
    thinking_steps: Optional[list[dict[str, Any]]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SendMessageRequest(BaseModel):
    conversation_id: str
    content: str = Field(..., min_length=1, max_length=4000)


class RegenerateRequest(BaseModel):
    conversation_id: str


class ChatResponse(BaseModel):
    message: MessageResponse
    workflow: Optional[str] = None
    stage: Optional[str] = None
    emotion: Optional[dict[str, Any]] = None
    turn_id: Optional[str] = None


class ResourceRecommendationDemoScenario(BaseModel):
    """Read-only input context used by the resource recommendation demo."""

    message: str


class ResourceRecommendationDemoResponse(BaseModel):
    """Full result of a direct, non-persistent resource agent run."""

    scenario: ResourceRecommendationDemoScenario
    output: dict[str, Any]
    usage: dict[str, Any]
    latency_ms: int


class StudyBuddyDemoScenario(BaseModel):
    """Read-only input context used by the study-buddy recommendation demo."""

    message: str


class StudyBuddyDemoResponse(BaseModel):
    """Full result of a direct, non-persistent study-buddy agent run."""

    scenario: StudyBuddyDemoScenario
    output: dict[str, Any]
    usage: dict[str, Any]
    latency_ms: int


class StudyBuddyDirectRequest(BaseModel):
    """The completed learning turn used by the direct buddy recommendation."""

    user_message: str = Field(..., min_length=1, max_length=4000)
    assistant_message: str = Field(..., min_length=1, max_length=12000)


class StudyBuddyDirectResponse(BaseModel):
    output: dict[str, Any]
    usage: dict[str, Any]
    latency_ms: int


class HistoryQueryParams(BaseModel):
    conversation_id: str
    before_id: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=100)


# ── Feedback ──────────────────────────────────────────────────────────

class MessageFeedbackRequest(BaseModel):
    message_id: str
    feedback_type: str = Field(..., pattern="^(thumb_up|thumb_down)$")
    comment: Optional[str] = None


class MessageFeedbackResponse(BaseModel):
    id: str
    message_id: str
    feedback_type: str
    comment: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionQuestionnaireRequest(BaseModel):
    q1_score: int = Field(..., ge=1, le=3)
    q2_score: int = Field(..., ge=1, le=3)
    q3_score: int = Field(..., ge=1, le=3)


class SessionQuestionnaireResponse(BaseModel):
    id: str
    conversation_id: str
    user_id: str
    q1_score: int
    q2_score: int
    q3_score: int
    total_score: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Pagination ────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int
    has_next: bool


# ── Knowledge graph (user-facing) ─────────────────────────────────────


class KnowledgeNodeSummary(BaseModel):
    """Lightweight knowledge node used in conversation list & detail views."""

    id: str
    label: str
    mastery: Optional[float] = None
    status: Optional[str] = None


class KnowledgeGraphNode(BaseModel):
    id: str
    label: str
    mastery: Optional[float] = None
    status: Optional[str] = None


class KnowledgeGraphEdge(BaseModel):
    source: str
    target: str


class KnowledgeGraphResponse(BaseModel):
    nodes: list[KnowledgeGraphNode]
    edges: list[KnowledgeGraphEdge]


# ── Agent execution per turn ──────────────────────────────────────────


class AgentTurnLogResponse(BaseModel):
    agent_name: str
    started_at: datetime
    duration_ms: int
    is_focus: bool = False
    output: Optional[dict[str, Any]] = None


# ── Agents ────────────────────────────────────────────────────────────


class AgentConfigResponse(BaseModel):
    """Effective LLM configuration of one registered agent.

    Mirrors what ``BaseAgent.execute`` would actually use – YAML value when
    present, global ``settings.llm`` fallback otherwise. Never contains
    credentials.
    """

    agent: str
    model: str
    base_url: str
    temperature: float
    max_tokens: int
    thinking: bool
    timeout: int
    max_retries: int
