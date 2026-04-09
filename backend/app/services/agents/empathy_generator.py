"""Empathy Generator Agent – empathetic response crafting."""

from __future__ import annotations

from typing import Any

from app.services.agents.base_agent import BaseAgent


class EmpathyGeneratorAgent(BaseAgent):
    config_file = "empathy_generator"
