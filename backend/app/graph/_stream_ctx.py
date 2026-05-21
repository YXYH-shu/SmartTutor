"""Out-of-band transport for SSE step_queue and agent_labels.

These objects (asyncio.Queue, dict) cannot live inside LangGraph state
because the checkpointer serialises state with msgpack.  Instead the
engine sets them as ContextVars before the graph run, and
stage_executor / agent_node read them via these vars.
"""

from __future__ import annotations

import contextvars
from typing import Any

# Set by engine._stream_graph_with_steps; read by stage_executor / agent_node.
step_queue_var: contextvars.ContextVar[Any | None] = contextvars.ContextVar(
    "_step_queue", default=None
)
agent_labels_var: contextvars.ContextVar[dict[str, str]] = contextvars.ContextVar(
    "_agent_labels", default={}
)
