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
    last_message: Optional[str] = None  # preview

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


# ── Pagination ────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int
    has_next: bool
