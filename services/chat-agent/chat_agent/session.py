from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from chat_agent.events import AgentEvent
from chat_agent.models import OrchestrationResult


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class ChatSession:
    session_id: str = field(default_factory=lambda: uuid4().hex)
    messages: list[ChatMessage] = field(default_factory=list)
    slots: dict[str, Any] = field(default_factory=dict)
    pending_skill: str | None = None
    pending_inputs: list[str] = field(default_factory=list)
    last_result: OrchestrationResult | None = None
    events: list[AgentEvent] = field(default_factory=list)

    def add_message(self, role: str, content: str) -> None:
        self.messages.append(ChatMessage(role=role, content=content))

    def add_event(self, event_type: str, message: str, **data: Any) -> None:
        self.events.append(AgentEvent(type=event_type, message=message, data=data))

    def update_slots(self, inputs: dict[str, Any]) -> None:
        for key, value in inputs.items():
            if value is not None and value != "":
                self.slots[key] = value

    def clear_pending(self) -> None:
        self.pending_skill = None
        self.pending_inputs = []
