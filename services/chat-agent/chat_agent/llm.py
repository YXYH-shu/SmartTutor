from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Sequence

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field, SecretStr


class OpenAICompatibleChatModel(BaseChatModel):
    model: str
    base_url: str
    api_key: SecretStr
    timeout: float = 60.0
    temperature: float = 0.0
    tools: list[dict[str, Any]] = Field(default_factory=list)
    tool_choice: str | None = None

    @property
    def _llm_type(self) -> str:
        return "openai-compatible-chat-completions"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | BaseTool | Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ):
        formatted_tools = [convert_to_openai_tool(tool) for tool in tools]
        return self.model_copy(update={"tools": formatted_tools, "tool_choice": tool_choice})

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [_message_to_openai(message) for message in messages],
            "temperature": self.temperature,
        }
        if self.tools:
            payload["tools"] = self.tools
        if self.tool_choice:
            payload["tool_choice"] = self.tool_choice
        if stop:
            payload["stop"] = stop

        _write_llm_context_log(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "model": self.model,
                "base_url": self.base_url,
                "temperature": self.temperature,
                "payload": payload,
            }
        )

        with httpx.Client(trust_env=False, timeout=self.timeout) as client:
            response = client.post(
                _chat_completions_url(self.base_url),
                headers={
                    "Authorization": f"Bearer {self.api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        response.raise_for_status()
        data = response.json()
        message = data["choices"][0]["message"]
        ai_message = AIMessage(
            content=message.get("content") or "",
            tool_calls=_parse_tool_calls(message.get("tool_calls") or []),
            response_metadata={
                "model": data.get("model"),
                "finish_reason": data["choices"][0].get("finish_reason"),
            },
        )
        return ChatResult(generations=[ChatGeneration(message=ai_message)], llm_output={"token_usage": data.get("usage")})


def _chat_completions_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/chat/completions"


def _write_llm_context_log(record: dict[str, Any]) -> None:
    log_path = Path(os.getenv("CHATAGENT_LLM_CONTEXT_LOG") or _default_llm_context_log_path())
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as file_obj:
        file_obj.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _default_llm_context_log_path() -> Path:
    return Path(__file__).resolve().parents[1] / "logs" / "llm_context.jsonl"


def _message_to_openai(message: BaseMessage) -> dict[str, Any]:
    content = _content_to_openai(message.content)
    if isinstance(message, SystemMessage):
        return {"role": "system", "content": content}
    if isinstance(message, HumanMessage):
        return {"role": "user", "content": content}
    if isinstance(message, ToolMessage):
        return {"role": "tool", "tool_call_id": message.tool_call_id, "content": content}
    if isinstance(message, AIMessage):
        payload: dict[str, Any] = {"role": "assistant", "content": content}
        if message.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": tool_call.get("id"),
                    "type": "function",
                    "function": {
                        "name": tool_call["name"],
                        "arguments": json.dumps(tool_call.get("args") or {}, ensure_ascii=False),
                    },
                }
                for tool_call in message.tool_calls
            ]
        return payload
    role = message.type if message.type in {"system", "user", "assistant", "tool"} else "user"
    return {"role": role, "content": content}


def _content_to_openai(content: str | list[str | dict[str, Any]]) -> str | list[str | dict[str, Any]]:
    return content


def _parse_tool_calls(raw_tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tool_calls: list[dict[str, Any]] = []
    for raw_call in raw_tool_calls:
        function = raw_call.get("function") or {}
        arguments = function.get("arguments") or "{}"
        try:
            parsed_args = json.loads(arguments)
        except json.JSONDecodeError:
            parsed_args = {"_raw_arguments": arguments}
        tool_calls.append(
            {
                "name": function.get("name", ""),
                "args": parsed_args,
                "id": raw_call.get("id"),
                "type": "tool_call",
            }
        )
    return tool_calls
