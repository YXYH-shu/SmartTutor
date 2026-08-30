from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.services.llm_client import LLMClient, _SlidingWindowLimiter


def _response(*, content: str | None, reasoning: str | None, completion_tokens: int):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=content,
                    reasoning_content=reasoning,
                )
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=100,
            completion_tokens=completion_tokens,
            total_tokens=100 + completion_tokens,
        ),
    )


@pytest.mark.asyncio
async def test_rate_limiter_caps_a_single_request_larger_than_tpm_budget():
    limiter = _SlidingWindowLimiter(rpm=0, tpm=100)

    await asyncio.wait_for(limiter.acquire(200), timeout=0.2)

    assert limiter._events[0][1] == 100


@pytest.mark.asyncio
async def test_json_mode_retries_without_thinking_when_only_reasoning_is_returned(
    monkeypatch,
):
    completion = AsyncMock(
        side_effect=[
            _response(
                content="",
                reasoning="这是推理过程，不是 JSON。",
                completion_tokens=16384,
            ),
            _response(
                content='{"status": "ok"}',
                reasoning=None,
                completion_tokens=20,
            ),
        ]
    )
    client = object.__new__(LLMClient)
    client._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=completion))
    )
    client._default_model = "glm-5"
    client._default_max_tokens = 16384
    client._max_retries = 3
    monkeypatch.setattr(settings.llm, "enable_thinking", True)
    monkeypatch.setattr(settings.llm, "max_retries", 3)

    result = await client.chat_completion(
        "返回 JSON",
        model="glm-5",
        max_tokens=16384,
        response_format="json",
        thinking=True,
    )

    assert result["content"] == {"status": "ok"}
    assert completion.await_count == 2
    assert completion.await_args_list[0].kwargs["extra_body"] == {
        "thinking": {"type": "enabled"}
    }
    assert completion.await_args_list[1].kwargs["extra_body"] == {
        "thinking": {"type": "disabled"}
    }
