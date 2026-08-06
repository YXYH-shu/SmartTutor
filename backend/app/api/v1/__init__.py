"""API v1 package – aggregates all routers."""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as users_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.chat import router as chat_router
from app.api.v1.agent_demos import router as agent_demos_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(conversations_router)
api_router.include_router(chat_router)
api_router.include_router(agent_demos_router)
