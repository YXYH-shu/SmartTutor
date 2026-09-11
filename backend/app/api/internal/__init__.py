"""课题五接入标准接口 (/internal/v1)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.internal.tutoring import router as tutoring_router

internal_router = APIRouter(prefix="/internal/v1")
internal_router.include_router(tutoring_router)
