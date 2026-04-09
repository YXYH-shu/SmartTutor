"""Conversation schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    user_id: str
    title: str | None = Field(default="新对话", max_length=255)
    workflow_type: str | None = Field(default=None, max_length=64)


class ConversationResponse(BaseModel):
    id: str
    user_id: str
    title: str | None
    workflow_type: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
