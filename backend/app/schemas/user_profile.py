"""UserProfile schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class UserProfileUpdate(BaseModel):
    knowledge_graph: dict[str, Any] | None = None
    learning_style: str | None = None
    current_level: str | None = None
    weak_points: list[Any] | None = None
    preferences: dict[str, Any] | None = None


class UserProfileResponse(BaseModel):
    id: str
    user_id: str
    knowledge_graph: dict[str, Any]
    learning_style: str | None
    current_level: str
    weak_points: list[Any]
    preferences: dict[str, Any]
    last_diagnosis: datetime | None
    updated_at: datetime

    model_config = {"from_attributes": True}
