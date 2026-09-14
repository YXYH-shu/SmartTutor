"""Simple in-memory rate limiter middleware.

For production, replace with Redis-backed implementation or ``slowapi``.
Uses a sliding-window counter per client IP.
"""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

# ── Config ──────────────────────────────────────────────────────────
GENERAL_LIMIT = 30       # requests per minute (general)
CHAT_LIMIT = 10          # requests per minute (/chat/*)
WINDOW = 60              # seconds

# ── State ───────────────────────────────────────────────────────────
_buckets: dict[str, list[float]] = defaultdict(list)


def _is_limited(key: str, limit: int) -> bool:
    now = time.time()
    window_start = now - WINDOW
    timestamps = _buckets[key] = [t for t in _buckets[key] if t > window_start]
    if len(timestamps) >= limit:
        return True
    timestamps.append(now)
    return False


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Per-IP rate limiting.  Chat endpoints get a tighter limit."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path

        # Choose limit based on path
        limit = CHAT_LIMIT if "/chat/" in path else GENERAL_LIMIT
        bucket_key = f"{client_ip}:{path if '/chat/' in path else '*'}"

        if _is_limited(bucket_key, limit):
            if path.startswith("/internal/v1/"):
                return JSONResponse(
                    status_code=200,
                    content={
                        "code": "500001",
                        "message": "接口限流，请稍后重试",
                        "requestId": request.headers.get("requestId", ""),
                        "data": {"retryAfterMs": WINDOW * 1000},
                    },
                )
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
            )

        return await call_next(request)
