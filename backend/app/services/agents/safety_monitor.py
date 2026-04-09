"""Safety Monitor Agent – content moderation & educational redirection."""

from __future__ import annotations

from typing import Any

from app.services.agents.base_agent import BaseAgent


class SafetyMonitorAgent(BaseAgent):
    config_file = "safety_monitor"
