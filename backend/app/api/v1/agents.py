"""Read-only agent registry endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.schemas import AgentConfigResponse
from app.config import settings
from app.services.agents import AGENT_REGISTRY, BaseAgent, list_agents
from app.services.llm_client import LLMClient

router = APIRouter(prefix="/agents", tags=["agents"])


def _effective_llm_config(agent: BaseAgent) -> dict[str, Any]:
    """Resolve the values ``agent.execute`` would actually send.

    Resolution order mirrors ``BaseAgent.__init__`` / ``LLMClient.__init__``:
    values already baked into the agent's LLMClient win, YAML ``llm_config``
    comes next, global ``settings.llm`` is the last fallback.
    """
    cfg = agent.llm_config
    llm = getattr(agent, "llm", None)
    if isinstance(llm, LLMClient):
        timeout = llm._client.timeout
        # openai SDK keeps whatever was passed in – int here, httpx.Timeout elsewhere
        timeout = getattr(timeout, "read", timeout)
        return {
            "model": llm._default_model,
            "base_url": str(llm._client.base_url or ""),
            # temperature/thinking are per-call, taken from YAML at execute time
            "temperature": cfg.get("temperature", 0.7),
            "max_tokens": llm._default_max_tokens,
            "thinking": bool(cfg.get("thinking", False)),
            "timeout": int(timeout) if timeout is not None else settings.llm.timeout,
            "max_retries": llm._client.max_retries,
        }
    return {
        "model": cfg.get("model") or settings.llm.model_name,
        "base_url": cfg.get("base_url") or settings.llm.base_url,
        "temperature": cfg.get("temperature", 0.7),
        "max_tokens": cfg.get("max_tokens") or settings.llm.max_tokens,
        "thinking": bool(cfg.get("thinking", False)),
        "timeout": cfg.get("timeout") or settings.llm.timeout,
        "max_retries": cfg.get("max_retries") or settings.llm.max_retries,
    }


@router.get("/configs", response_model=list[AgentConfigResponse])
async def list_agent_configs() -> list[AgentConfigResponse]:
    """Return the effective LLM configuration of every registered agent."""
    list_agents()  # populate the registry on first call (no-op afterwards)
    configs: list[AgentConfigResponse] = []
    for agent in AGENT_REGISTRY.values():
        if not isinstance(agent, BaseAgent):
            continue
        configs.append(AgentConfigResponse(agent=agent.name, **_effective_llm_config(agent)))
    return configs
