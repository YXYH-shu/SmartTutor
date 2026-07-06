"""Unified LLM client supporting OpenAI-compatible APIs (OpenAI / vLLM).

Features:
- Async OpenAI SDK
- Exponential-backoff retry
- JSON response mode with parse-tolerant fallback
- jsonschema validation with LLM-assisted auto-repair
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

from jsonschema import ValidationError, validate as jsonschema_validate
from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Thin wrapper around ``openai.AsyncOpenAI`` with retry & JSON helpers."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
    ) -> None:
        self._client = AsyncOpenAI(
            base_url=base_url or settings.llm.base_url,
            api_key=api_key or settings.llm.api_key,
            max_retries=max_retries if max_retries is not None else settings.llm.max_retries,
            timeout=timeout if timeout is not None else settings.llm.timeout,
        )
        self._default_model = model or settings.llm.model_name
        self._default_max_tokens = max_tokens if max_tokens is not None else settings.llm.max_tokens

    # ------------------------------------------------------------------
    # Core completion
    # ------------------------------------------------------------------

    async def chat_completion(
        self,
        prompt: str,
        system_prompt: str | None = None,
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        response_format: str = "json",
        thinking: bool = False,
    ) -> dict[str, Any]:
        """Send a chat completion request and return a structured dict.

        Returns
        -------
        dict  {"content": str | dict, "usage": dict, "latency_ms": int}
        """
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        json_mode = response_format == "json"
        # Use per-client or global default max_tokens if not explicitly provided
        _max_tokens = max_tokens if max_tokens is not None else self._default_max_tokens
        # Build kwargs – only add response_format if the backend supports it
        kwargs: dict[str, Any] = dict(
            model=model or self._default_model,
            messages=messages,
            temperature=temperature,
            max_tokens=_max_tokens,
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        # if thinking:
        #     kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

        last_exc: Exception | None = None
        used_json_mode = json_mode  # track whether we already tried without it

        for attempt in range(1, settings.llm.max_retries + 1):
            t0 = time.perf_counter()
            try:
                resp = await self._client.chat.completions.create(**kwargs)
            except Exception as exc:
                last_exc = exc
                if _is_content_filter_error(exc):
                    logger.warning("LLM content filter triggered (non-retryable): %s", exc)
                    raise RuntimeError(f"LLM content filter blocked the request: {exc}") from exc
                wait = 2 ** attempt * 0.5
                logger.warning("LLM request failed (attempt %d): %s – retry in %.1fs", attempt, exc, wait)
                await asyncio.sleep(wait)
                continue

            latency_ms = int((time.perf_counter() - t0) * 1000)
            msg = resp.choices[0].message
            raw_text = msg.content or ""

            # Reasoning models (glm-5, DeepSeek-R1, etc.) may put output in
            # reasoning_content while leaving content empty.  Try that field.
            if not raw_text.strip():
                for attr in ("reasoning_content", "reasoning"):
                    candidate = getattr(msg, attr, None)
                    if candidate and isinstance(candidate, str) and candidate.strip():
                        logger.info("LLM content empty, using %s (%d chars)", attr, len(candidate))
                        raw_text = candidate
                        break

            # Still empty — if using response_format, retry WITHOUT it once.
            # Some models don't support json_object mode and return blank content.
            if not raw_text.strip() and json_mode and used_json_mode:
                logger.warning("LLM returned empty content with json_mode – retrying without response_format")
                kwargs.pop("response_format", None)
                used_json_mode = False
                continue

            if not raw_text.strip():
                last_exc = RuntimeError("LLM returned empty content")
                wait = 2 ** attempt * 0.5
                logger.warning("LLM returned empty content (attempt %d) – retry in %.1fs", attempt, wait)
                await asyncio.sleep(wait)
                continue

            usage = {}
            if resp.usage:
                usage = {
                    "prompt_tokens": resp.usage.prompt_tokens,
                    "completion_tokens": resp.usage.completion_tokens,
                    "total_tokens": resp.usage.total_tokens,
                }

            # Trace: log LLM I/O
            from app.services.trace_logger import get_trace_logger
            _tl = get_trace_logger()
            _tl.debug("LLM_CALL   model=%s temp=%.2f max_tokens=%d thinking=%s",
                      kwargs["model"], temperature, _max_tokens, thinking)
            for m in messages:
                _tl.debug("LLM_PROMPT | [%s] %s", m["role"], m["content"][:3000])
            _tl.debug("LLM_RESPONSE | %s", raw_text[:3000])
            _tl.debug("LLM_LATENCY %dms prompt_tokens=%s completion_tokens=%s",
                      latency_ms, usage.get("prompt_tokens"), usage.get("completion_tokens"))

            content: str | dict = raw_text
            if json_mode:
                content = _parse_json_text(raw_text)

            return {"content": content, "usage": usage, "latency_ms": latency_ms}

        # All retries exhausted
        raise RuntimeError(f"LLM request failed after {settings.llm.max_retries} attempts") from last_exc

    # ------------------------------------------------------------------
    # JSON schema validation with auto-repair
    # ------------------------------------------------------------------

    async def validate_json_response(
        self,
        response: str | dict,
        schema: dict[str, Any],
        *,
        max_repair_attempts: int = 1,
    ) -> dict[str, Any]:
        """Validate *response* against *schema*.

        If validation fails, attempt to let the LLM fix the JSON once.
        """
        data = response if isinstance(response, dict) else _parse_json_text(response)

        first_err_msg: str | None = None
        try:
            jsonschema_validate(instance=data, schema=schema)
            return data
        except ValidationError as err:
            first_err_msg = err.message
            logger.warning("JSON schema validation failed: %s", first_err_msg)

        # --- auto-repair loop ---
        for _ in range(max_repair_attempts):
            repair_prompt = (
                "以下JSON不符合指定的Schema，请修正并返回合法JSON。\n\n"
                f"原始JSON:\n{json.dumps(data, ensure_ascii=False, indent=2)}\n\n"
                f"要求的Schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
                "仅返回修正后的JSON，不要添加任何解释。"
            )
            result = await self.chat_completion(
                prompt=repair_prompt,
                system_prompt="你是一个JSON格式修复助手。",
                temperature=0.1,
                response_format="json",
            )
            repaired = result["content"] if isinstance(result["content"], dict) else _parse_json_text(result["content"])
            try:
                jsonschema_validate(instance=repaired, schema=schema)
                return repaired
            except ValidationError:
                continue

        raise ValueError(f"JSON schema validation failed after repair attempts: {first_err_msg}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_content_filter_error(exc: Exception) -> bool:
    """Detect non-retryable content filter / safety errors from LLM APIs."""
    exc_str = str(exc)
    # GLM API: error code 1301 (content safety filter)
    if "'code': '1301'" in exc_str or '"code": "1301"' in exc_str:
        return True
    # Generic contentFilter markers
    if "contentFilter" in exc_str:
        return True
    # OpenAI-style content policy refusal (400 with "content_policy" or "safety")
    if "content_policy" in exc_str or "content management policy" in exc_str:
        return True
    return False


def _parse_json_text(text: str) -> dict:
    """Extract and parse JSON from LLM output (tolerates markdown fences)."""
    # Strip markdown code fences if present
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find first { ... } block
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise
