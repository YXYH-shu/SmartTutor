"""Study Buddy Agent – peer learning partner recommendations."""

from __future__ import annotations

from typing import Any

from app.services.agents.base_agent import BaseAgent


class StudyBuddyAgent(BaseAgent):
    config_file = "study_buddy"
