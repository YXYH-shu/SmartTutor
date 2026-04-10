"""Agent registry – auto-registers all 9 education agents.

Usage::

    from app.services.agents import get_agent, list_agents

    agent = get_agent("safety_monitor")
    result = await agent.execute({"raw_text": "...", "user_age": 15})
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.agents.base_agent import BaseAgent
from app.services.agents.safety_monitor import SafetyMonitorAgent
from app.services.agents.emotion_analyzer import EmotionAnalyzerAgent
from app.services.agents.cognitive_diagnosis import CognitiveDiagnosisAgent
from app.services.agents.learning_path import LearningPathAgent
from app.services.agents.resource_recommender import ResourceRecommenderAgent
from app.services.agents.study_buddy import StudyBuddyAgent
from app.services.agents.empathy_generator import EmpathyGeneratorAgent
from app.services.agents.content_polisher import ContentPolisherAgent
from app.services.agents.knowledge_responder import KnowledgeResponderAgent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

AGENT_REGISTRY: dict[str, BaseAgent] = {}


def register_agent(agent: BaseAgent) -> None:
    """Register an agent instance into the global registry."""
    AGENT_REGISTRY[agent.name] = agent
    logger.debug("Registered agent: %s", agent.name)


def get_agent(name: str) -> BaseAgent:
    """Retrieve a registered agent by name. Raises KeyError if not found."""
    if not AGENT_REGISTRY:
        _auto_register()
    return AGENT_REGISTRY[name]


def list_agents() -> list[dict[str, Any]]:
    """Return metadata for all registered agents."""
    if not AGENT_REGISTRY:
        _auto_register()
    return [
        {
            "name": a.name,
            "description": a.description,
            "version": a.version,
        }
        for a in AGENT_REGISTRY.values()
    ]


# ---------------------------------------------------------------------------
# Auto-registration
# ---------------------------------------------------------------------------

_AGENT_CLASSES: list[type[BaseAgent]] = [
    SafetyMonitorAgent,
    EmotionAnalyzerAgent,
    CognitiveDiagnosisAgent,
    LearningPathAgent,
    ResourceRecommenderAgent,
    StudyBuddyAgent,
    EmpathyGeneratorAgent,
    ContentPolisherAgent,
    KnowledgeResponderAgent,
]


def _auto_register() -> None:
    """Instantiate and register all known agents."""
    for cls in _AGENT_CLASSES:
        try:
            register_agent(cls())
        except Exception:
            logger.warning("Failed to register agent %s", cls.__name__, exc_info=True)


__all__ = [
    "AGENT_REGISTRY",
    "register_agent",
    "get_agent",
    "list_agents",
    "BaseAgent",
    "SafetyMonitorAgent",
    "EmotionAnalyzerAgent",
    "CognitiveDiagnosisAgent",
    "LearningPathAgent",
    "ResourceRecommenderAgent",
    "StudyBuddyAgent",
    "EmpathyGeneratorAgent",
    "ContentPolisherAgent",
    "KnowledgeResponderAgent",
]
