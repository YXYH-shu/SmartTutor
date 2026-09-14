"""A minimal OpenAI-compatible chat-completions client.

The recommendation flow only needs three operations: JSON completion, text
completion, and streamed text completion.  Keeping this client small makes it
usable with OpenAI-compatible school/private deployments without tying the
application to a larger agent framework.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any


class LLMError(RuntimeError):
    """Base error for a failed language-model request."""


class LLMConfigurationError(LLMError):
    """Raised when the application has no usable LLM configuration."""


class LLMRequestError(LLMError):
    """Raised when the configured provider rejects or cannot serve a request."""


class LLMResponseError(LLMError):
    """Raised when a provider response is malformed for the requested mode."""


@dataclass(frozen=True)
class LLMResponse:
    """Normalised result of a non-streaming LLM completion."""

    content: str
    model: str | None = None
    data: dict[str, Any] | list[Any] | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class LLMClient:
    """Call a standard ``/chat/completions`` endpoint asynchronously.

    ``httpx`` is imported only while a request is made.  This keeps imports
    harmless in tooling/tests that do not install runtime dependencies, while
    production receives a clear configuration error instead of fabricated
    recommendation output.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.base_url = (
            base_url
            or os.getenv("SCIENCE_HUB_LLM_BASE_URL")
            or os.getenv("RECOMMENDATION_LLM_BASE_URL")
            or ""
        ).strip()
        self.api_key = (
            api_key
            or os.getenv("SCIENCE_HUB_LLM_API_KEY")
            or os.getenv("RECOMMENDATION_LLM_API_KEY")
            or ""
        ).strip()
        self.model = (
            model
            or os.getenv("SCIENCE_HUB_LLM_MODEL")
            or os.getenv("RECOMMENDATION_LLM_MODEL")
            or ""
        ).strip()
        self.timeout_seconds = timeout_seconds or _float_env(
            "SCIENCE_HUB_LLM_TIMEOUT_SECONDS", 90.0
        )

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    async def complete_json(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Request a JSON object and reject non-JSON model output."""

        response = await self._complete(
            prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        try:
            data = _parse_json(response.content)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise LLMResponseError("模型没有返回可解析的 JSON 结果") from exc
        return LLMResponse(
            content=response.content,
            model=response.model,
            data=data,
            raw=response.raw,
        )

    async def complete_text(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Request one complete text response."""

        return await self._complete(
            prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def stream_text(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Yield text deltas from an OpenAI-style Server-Sent Event stream."""

        httpx = _load_httpx()
        self._require_configuration()
        payload = self._payload(
            prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                async with client.stream(
                    "POST", self._endpoint(), headers=self._headers(), json=payload
                ) as response:
                    if response.is_error:
                        body = await response.aread()
                        raise LLMRequestError(_provider_error_message(response.status_code, body))
                    async for line in response.aiter_lines():
                        value = line.strip()
                        if not value or not value.startswith("data:"):
                            continue
                        encoded = value[5:].strip()
                        if encoded == "[DONE]":
                            return
                        try:
                            event = json.loads(encoded)
                        except json.JSONDecodeError as exc:
                            raise LLMResponseError("模型流返回了无效事件") from exc
                        delta = _stream_delta(event)
                        if delta:
                            yield delta
        except LLMError:
            raise
        except Exception as exc:  # httpx is deliberately not imported at module load.
            raise LLMRequestError("调用语言模型服务失败") from exc

    async def _complete(
        self,
        prompt: str,
        *,
        system_prompt: str | None,
        temperature: float,
        max_tokens: int | None,
    ) -> LLMResponse:
        httpx = _load_httpx()
        self._require_configuration()
        payload = self._payload(
            prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    self._endpoint(), headers=self._headers(), json=payload
                )
            if response.is_error:
                raise LLMRequestError(_provider_error_message(response.status_code, response.content))
            raw = response.json()
        except LLMError:
            raise
        except Exception as exc:
            raise LLMRequestError("调用语言模型服务失败") from exc

        content = _completion_content(raw)
        return LLMResponse(
            content=content,
            model=str(raw.get("model") or self.model),
            raw=raw if isinstance(raw, dict) else {},
        )

    def _require_configuration(self) -> None:
        missing = [
            name
            for name, value in (
                ("SCIENCE_HUB_LLM_BASE_URL", self.base_url),
                ("SCIENCE_HUB_LLM_API_KEY", self.api_key),
                ("SCIENCE_HUB_LLM_MODEL", self.model),
            )
            if not value
        ]
        if missing:
            raise LLMConfigurationError(
                "语言模型尚未配置（缺少 " + "、".join(missing) + "）"
            )

    def _endpoint(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream, application/json",
        }

    def _payload(
        self,
        prompt: str,
        *,
        system_prompt: str | None,
        temperature: float,
        max_tokens: int | None,
        stream: bool,
    ) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        return payload


def _load_httpx() -> Any:
    try:
        import httpx
    except ImportError as exc:  # pragma: no cover - deployment dependency
        raise LLMConfigurationError("缺少 httpx，无法调用语言模型服务") from exc
    return httpx


def _completion_content(raw: Any) -> str:
    if not isinstance(raw, Mapping):
        raise LLMResponseError("模型响应不是 JSON 对象")
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMResponseError("模型响应缺少 choices")
    first = choices[0]
    if not isinstance(first, Mapping):
        raise LLMResponseError("模型响应 choices 无效")
    message = first.get("message")
    if not isinstance(message, Mapping):
        raise LLMResponseError("模型响应缺少 message")
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(
            str(item.get("text") or "") if isinstance(item, Mapping) else str(item)
            for item in content
        )
    if not isinstance(content, str) or not content.strip():
        raise LLMResponseError("模型响应没有文本内容")
    return content.strip()


def _stream_delta(event: Any) -> str:
    if not isinstance(event, Mapping):
        return ""
    choices = event.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    choice = choices[0]
    if not isinstance(choice, Mapping):
        return ""
    delta = choice.get("delta")
    if not isinstance(delta, Mapping):
        return ""
    content = delta.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(item.get("text") or "") if isinstance(item, Mapping) else ""
            for item in content
        )
    return ""


def _parse_json(content: str) -> dict[str, Any] | list[Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        stripped = stripped[first_newline + 1 :] if first_newline >= 0 else stripped
        if stripped.endswith("```"):
            stripped = stripped[:-3]
        stripped = stripped.strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        start = min(
            (position for position in (stripped.find("{"), stripped.find("[")) if position >= 0),
            default=-1,
        )
        end = max(stripped.rfind("}"), stripped.rfind("]"))
        if start < 0 or end <= start:
            raise
        value = json.loads(stripped[start : end + 1])
    if not isinstance(value, (dict, list)):
        raise ValueError("JSON result must be an object or array")
    return value


def _provider_error_message(status_code: int, body: bytes | str) -> str:
    try:
        decoded = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else body
        payload = json.loads(decoded)
        if isinstance(payload, Mapping):
            error = payload.get("error")
            if isinstance(error, Mapping) and error.get("message"):
                return f"语言模型服务返回 {status_code}: {str(error['message'])[:240]}"
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return f"语言模型服务返回 HTTP {status_code}"


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default
