"""Resource Recommender Agent – personalised learning material suggestions."""

from __future__ import annotations

from typing import Any

from app.services.agents.base_agent import BaseAgent


class ResourceRecommenderAgent(BaseAgent):
    config_file = "resource_recommender"
