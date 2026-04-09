"""Message schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MessageCreate(BaseModel):
    conversation_id: str
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str
    agent_type: str | None = None
    emotion_state: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    agent_type: str | None
    emotion_state: dict[str, Any] | None
    metadata: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}
