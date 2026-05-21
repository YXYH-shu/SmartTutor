"""Trace logger – file-only runtime logging for LLM calls and graph node transitions.

Provides a dedicated logger ``app.trace`` that writes to a rotating file
without polluting the console.  Three logging layers:

- **Turn layer** (engine.py): TURN_START / TURN_END boundaries
- **Node layer** (graph nodes): NODE_ENTER / NODE_EXIT with key state fields
- **LLM layer** (llm_client.py): LLM_CALL / LLM_PROMPT / LLM_RESPONSE / LLM_LATENCY
"""

from __future__ import annotations

import logging
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOGGER_NAME = "app.trace"

_setup_done: bool = False


def _default_log_path() -> str:
    """Resolve to ``backend/logs/trace.log`` relative to this file's location."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    return str(backend_dir / "logs" / "trace.log")


def setup_trace_logger(
    *,
    log_path: str = "",
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> logging.Logger:
    """Create and configure the ``app.trace`` logger.  Idempotent."""
    global _setup_done
    logger = logging.getLogger(_LOGGER_NAME)

    if _setup_done:
        return logger

    if not log_path:
        log_path = _default_log_path()

    # Ensure parent directory exists
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s.%(msecs)03d %(levelname)-5s [%(name)s] %(message)s")
    )

    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False  # Do NOT send to root handler (console)

    _setup_done = True
    return logger


def get_trace_logger() -> logging.Logger:
    """Return the ``app.trace`` logger (must call ``setup_trace_logger`` first)."""
    return logging.getLogger(_LOGGER_NAME)


def generate_trace_id() -> str:
    """Generate a short trace ID like ``trace-a1b2c3d4e5f6``."""
    return f"trace-{uuid.uuid4().hex[:12]}"
