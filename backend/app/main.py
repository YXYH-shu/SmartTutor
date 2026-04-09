"""FastAPI application entry point – wires routes, middleware, and lifespan."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

logging.basicConfig(
    level=logging.DEBUG if settings.app.debug else logging.INFO,
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks."""
    # ── Startup ──────────────────────────────────────────────────
    if settings.app.debug:
        from app.database import init_db
        await init_db()

    # Pre-load agent registry so first request is fast
    from app.services.agents import list_agents
    agents = list_agents()
    logging.getLogger(__name__).info("Registered %d agents: %s", len(agents), [a["name"] for a in agents])

    yield

    # ── Shutdown ─────────────────────────────────────────────────
    from app.database import engine
    await engine.dispose()


app = FastAPI(
    title="Smart Tutor API",
    version="1.0.0",
    description="Intelligent tutoring agent system powered by LangGraph",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.app.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Custom middleware (order matters: outermost first) ───────────────
from app.middleware.error_handler import ErrorHandlerMiddleware
from app.middleware.logging_middleware import LoggingMiddleware
from app.middleware.rate_limiter import RateLimiterMiddleware

app.add_middleware(ErrorHandlerMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(RateLimiterMiddleware)

# ── Routes ───────────────────────────────────────────────────────────
from app.api.v1 import api_router

app.include_router(api_router)


# ── Health check ─────────────────────────────────────────────────────
@app.get("/health", tags=["system"])
async def health_check():
    """Lightweight liveness probe.  Checks DB connectivity."""
    try:
        from app.database import engine
        async with engine.connect() as conn:
            from sqlalchemy import text
            await conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"
    return {"status": "ok", "db": db_status}
