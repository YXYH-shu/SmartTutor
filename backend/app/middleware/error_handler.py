"""Error handling middleware – catches exceptions and returns structured JSON."""

from __future__ import annotations

import logging
import traceback

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Catch unhandled exceptions and return a consistent JSON body."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        try:
            return await call_next(request)
        except Exception as exc:
            logger.exception("Unhandled exception on %s %s", request.method, request.url.path)

            # Map common agent exceptions to user-friendly messages
            detail = "服务器内部错误，请稍后重试"
            status_code = 500

            exc_type = type(exc).__name__
            if "AgentExecution" in exc_type:
                detail = "智能体执行出错，请重试"
                status_code = 500
            elif "SafetyCheck" in exc_type:
                detail = "内容安全检查未通过"
                status_code = 400
            elif "Validation" in exc_type:
                detail = str(exc)
                status_code = 422

            return JSONResponse(
                status_code=status_code,
                content={"detail": detail, "error_type": exc_type},
            )
