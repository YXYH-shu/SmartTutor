"""Decision engine – LLM-powered router that decides which agents run next.

Loads its prompt from ``config/prompts/decision.yaml`` and workflow
definitions from ``config/workflows.yaml``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from langchain_core.messages import HumanMessage

from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
_PROMPTS_DIR = _CONFIG_DIR / "prompts"


class DecisionEngine:
    """Calls an LLM to decide the next step in the tutor graph."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._workflows: dict[str, Any] | None = None
        self._prompt_config: dict[str, Any] | None = None
        if llm is not None:
            self.llm = llm
        else:
            cfg = self.prompt_config.get("llm_config", {})
            self.llm = LLMClient(
                base_url=cfg.get("base_url"),
                api_key=cfg.get("api_key"),
                model=cfg.get("model"),
                max_tokens=cfg.get("max_tokens"),
                timeout=cfg.get("timeout"),
                max_retries=cfg.get("max_retries"),
            )

    # ------------------------------------------------------------------
    # Lazy-loaded configs
    # ------------------------------------------------------------------

    @property
    def workflows(self) -> dict[str, Any]:
        if self._workflows is None:
            path = _CONFIG_DIR / "workflows.yaml"
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            self._workflows = data
        return self._workflows

    @property
    def default_workflow(self) -> str:
        return self.workflows.get("default_workflow", "adaptive_learning")

    @property
    def prompt_config(self) -> dict[str, Any]:
        if self._prompt_config is None:
            path = _PROMPTS_DIR / "decision.yaml"
            with open(path, "r", encoding="utf-8") as fh:
                self._prompt_config = yaml.safe_load(fh)
        return self._prompt_config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def decide_next_step(
        self,
        state: dict[str, Any],
        available_agents: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Analyse *state* and return a decision dict.

        Returns
        -------
        dict with keys: decision, target_workflow, target_stage,
                        agent_sequence, reasoning
        """
        prompt = self._build_prompt(state, available_agents)
        llm_cfg = self.prompt_config.get("llm_config", {})

        result = await self.llm.chat_completion(
            prompt=prompt,
            model=llm_cfg.get("model"),
            temperature=llm_cfg.get("temperature", 0.2),
            max_tokens=llm_cfg.get("max_tokens"),
            response_format="json",
        )

        raw = result["content"]
        if not isinstance(raw, dict):
            # Parse-fallback
            import json
            raw = json.loads(raw)

        schema = self.prompt_config.get("output_schema", {})
        if schema:
            raw = await self.llm.validate_json_response(raw, schema)

        logger.info(
            "Decision: %s → agents=%s | %s",
            raw.get("decision"),
            raw.get("agent_sequence"),
            raw.get("reasoning"),
        )
        return raw

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        state: dict[str, Any],
        available_agents: list[dict[str, str]],
    ) -> str:
        from jinja2 import Environment, BaseLoader

        template_str = self.prompt_config.get("prompt_template", "")
        env = Environment(loader=BaseLoader())

        # Prepare recent messages (last 5 turns)
        messages = state.get("messages", [])
        recent = []
        for msg in messages[-10:]:  # last 5 turns = ~10 messages
            recent.append({
                "role": getattr(msg, "type", "unknown"),
                "content": getattr(msg, "content", ""),
            })

        # Emotion info
        emotion_history = state.get("emotion_history", [])
        latest_emotion = ""
        emotion_intensity = ""
        if emotion_history:
            last = emotion_history[-1] if isinstance(emotion_history[-1], dict) else {}
            latest_emotion = last.get("emotion", "未知")
            emotion_intensity = last.get("intensity", "未知")

        # Check if current stage is the last in its workflow
        is_last_stage = False
        current_wf = state.get("workflow_type")
        current_stg = state.get("current_stage")
        if current_wf and current_stg:
            is_last_stage = self.get_next_stage(current_wf, current_stg) is None

        template = env.from_string(template_str)
        return template.render(
            available_agents=available_agents,
            workflows=self.workflows.get("workflows", {}),
            current_workflow=current_wf,
            current_stage=current_stg,
            stage_counter=state.get("stage_counter", 0),
            is_last_stage=is_last_stage,
            latest_emotion=latest_emotion,
            emotion_intensity=emotion_intensity,
            recent_messages=recent,
        )

    # ------------------------------------------------------------------
    # Workflow helpers
    # ------------------------------------------------------------------

    def get_workflow(self, name: str) -> dict[str, Any] | None:
        return self.workflows.get("workflows", {}).get(name)

    def get_stage(self, workflow_name: str, stage_id: str) -> dict[str, Any] | None:
        wf = self.get_workflow(workflow_name)
        if not wf:
            return None
        for stage in wf.get("stages", []):
            if stage["id"] == stage_id:
                return stage
        return None

    def get_first_stage(self, workflow_name: str) -> dict[str, Any] | None:
        wf = self.get_workflow(workflow_name)
        if not wf or not wf.get("stages"):
            return None
        return wf["stages"][0]

    def get_next_stage(self, workflow_name: str, current_stage_id: str) -> dict[str, Any] | None:
        wf = self.get_workflow(workflow_name)
        if not wf:
            return None
        stages = wf.get("stages", [])
        for i, s in enumerate(stages):
            if s["id"] == current_stage_id and i + 1 < len(stages):
                return stages[i + 1]
        return None  # last stage reached
