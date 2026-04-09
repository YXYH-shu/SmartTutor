"""User schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserInDB(BaseModel):
    """Internal schema that includes the hashed password."""

    id: str
    username: str
    email: str
    hashed_password: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
