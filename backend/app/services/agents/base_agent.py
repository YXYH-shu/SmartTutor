"""Abstract base class for all education agents.

Every agent:
1. Loads its config (prompt template, schemas, LLM params) from a YAML file.
2. Renders the Jinja2 prompt template with runtime input_data.
3. Calls LLMClient → validates JSON output against output_schema.
4. Persists an AgentExecutionLog row.
5. Optionally updates UserProfile when the agent produces profile-level insights.
"""

from __future__ import annotations

import abc
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

import yaml
from jinja2 import BaseLoader, Environment, StrictUndefined
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.agent_execution_log import AgentExecutionLog
from app.models.user_profile import UserProfile
from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "config" / "prompts"

_jinja_env = Environment(loader=BaseLoader(), undefined=StrictUndefined)


class BaseAgent(abc.ABC):
    """All concrete agents must subclass this."""

    # Subclasses may override to point at a different YAML stem
    config_file: str = ""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._config: dict[str, Any] | None = None
        if llm is not None:
            self.llm = llm
        else:
            cfg = self.llm_config
            self.llm = LLMClient(
                base_url=cfg.get("base_url"),
                api_key=cfg.get("api_key"),
                model=cfg.get("model"),
                max_tokens=cfg.get("max_tokens"),
                timeout=cfg.get("timeout"),
                max_retries=cfg.get("max_retries"),
            )

    # ------------------------------------------------------------------
    # Config lazy-load
    # ------------------------------------------------------------------

    @property
    def config(self) -> dict[str, Any]:
        if self._config is None:
            self._config = self._load_config()
        return self._config

    def _load_config(self) -> dict[str, Any]:
        stem = self.config_file or self.name
        path = _PROMPTS_DIR / f"{stem}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Prompt config not found: {path}")
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)

    # ------------------------------------------------------------------
    # Descriptors (sourced from YAML config)
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self.config.get("name", self.__class__.__name__.lower())

    @property
    def description(self) -> str:
        return self.config.get("description", "")

    @property
    def version(self) -> str:
        return self.config.get("version", "0.1")

    @property
    def input_schema(self) -> dict[str, Any]:
        return self.config.get("input_schema", {})

    @property
    def output_schema(self) -> dict[str, Any]:
        return self.config.get("output_schema", {})

    @property
    def system_prompt_template(self) -> str:
        return self.config.get("prompt_template", "")

    @property
    def llm_config(self) -> dict[str, Any]:
        return self.config.get("llm_config", {})

    # ------------------------------------------------------------------
    # Execute pipeline
    # ------------------------------------------------------------------

    async def execute(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Full execution pipeline: enrich → render → call LLM → validate → log."""
        context = context or {}
        t0 = time.perf_counter()

        # 1. Enrich input_data with DB-sourced context (subclasses override)
        enriched = await self.enrich_input(input_data, context)

        # 2. Render prompt
        rendered = self._render_prompt(enriched)

        # 3. Call LLM – model/temperature/max_tokens use config defaults unless YAML overrides
        llm_cfg = self.llm_config
        llm_result = await self.llm.chat_completion(
            prompt=rendered,
            system_prompt=None,  # prompt_template already contains system instructions
            model=llm_cfg.get("model"),           # None → uses client default
            temperature=llm_cfg.get("temperature", 0.7),
            max_tokens=llm_cfg.get("max_tokens"),  # None → uses client default
            response_format="json",
        )

        # 4. Validate JSON output
        raw_content = llm_result["content"]
        if self.output_schema:
            validated = await self.llm.validate_json_response(raw_content, self.output_schema)
        else:
            validated = raw_content if isinstance(raw_content, dict) else {}

        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        # 5. Persist execution log
        await self._log_execution(
            conversation_id=context.get("conversation_id", ""),
            input_payload=enriched,
            output_payload=validated,
            execution_time_ms=elapsed_ms,
        )

        # 6. Post-process (subclasses override to e.g. update UserProfile)
        await self.post_process(validated, context)

        return {
            "agent": self.name,
            "output": validated,
            "usage": llm_result.get("usage", {}),
            "latency_ms": elapsed_ms,
        }

    # ------------------------------------------------------------------
    # Hooks for subclasses
    # ------------------------------------------------------------------

    async def enrich_input(self, input_data: dict, context: dict) -> dict:
        """Pull extra context from DB before rendering the prompt.

        Default: attach user profile if user_id is present.
        """
        user_id = input_data.get("user_id") or context.get("user_id")
        if user_id:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(UserProfile).where(UserProfile.user_id == user_id)
                )
                profile = result.scalar_one_or_none()
                if profile:
                    input_data["user_profile"] = {
                        "knowledge_graph": profile.knowledge_graph,
                        "learning_style": profile.learning_style,
                        "current_level": profile.current_level,
                        "weak_points": profile.weak_points,
                        "preferences": profile.preferences,
                    }
        return input_data

    async def post_process(self, output: dict, context: dict) -> None:
        """Hook called after successful validation. Override in subclasses."""
        pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _render_prompt(self, data: dict[str, Any]) -> str:
        template = _jinja_env.from_string(self.system_prompt_template)
        return template.render(**data)

    async def _log_execution(
        self,
        conversation_id: str,
        input_payload: dict,
        output_payload: dict,
        execution_time_ms: int,
    ) -> None:
        if not conversation_id:
            logger.info("No conversation_id – skipping execution log for %s", self.name)
            return
        async with AsyncSessionLocal() as session:
            log = AgentExecutionLog(
                id=str(uuid.uuid4()),
                conversation_id=conversation_id,
                agent_name=self.name,
                input_payload=input_payload,
                output_payload=output_payload,
                execution_time_ms=execution_time_ms,
            )
            session.add(log)
            await session.commit()
