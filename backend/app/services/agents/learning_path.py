"""Learning Path Agent – personalised study plan generation."""

from __future__ import annotations

from typing import Any

from app.services.agents.base_agent import BaseAgent


class LearningPathAgent(BaseAgent):
    config_file = "learning_path"
