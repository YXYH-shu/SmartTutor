"""Knowledge Responder Agent – generates natural language responses from scratch."""

from __future__ import annotations

from app.services.agents.base_agent import BaseAgent


class KnowledgeResponderAgent(BaseAgent):
    config_file = "knowledge_responder"
