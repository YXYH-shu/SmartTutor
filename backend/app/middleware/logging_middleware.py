"""Request logging middleware – logs method, path, duration, user."""

from __future__ import annotations

import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger("app.access")


class LoggingMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request with method, path, status, duration."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)

        # Try to extract user_id from JWT (best-effort, no fail)
        user_id = "-"
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            try:
                import jwt as pyjwt
                from app.config import settings
                payload = pyjwt.decode(
                    auth[7:], settings.app.secret_key, algorithms=["HS256"]
                )
                user_id = payload.get("sub", "-")[:8]
            except Exception:
                pass

        logger.info(
            "%s %s → %d (%dms) user=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            user_id,
        )
        return response
