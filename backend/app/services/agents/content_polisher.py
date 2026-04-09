"""Content Polisher Agent – teaching content correction & refinement."""

from __future__ import annotations

from typing import Any

from app.services.agents.base_agent import BaseAgent


class ContentPolisherAgent(BaseAgent):
    config_file = "content_polisher"
