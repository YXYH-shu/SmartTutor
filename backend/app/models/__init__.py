"""SQLAlchemy ORM models for Smart Tutor."""

from app.models.user import User
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user_profile import UserProfile
from app.models.agent_execution_log import AgentExecutionLog
from app.models.checkpoint import Checkpoint
from app.models.message_feedback import MessageFeedback
from app.models.knowledge_point import KnowledgePoint
from app.models.learning_resource import LearningResource
from app.models.learner_interaction import (
    LearnerResourceInteraction,
    LearnerKnowledgeInteraction,
    LearnerLearnerRelation,
)
from app.models.recommendation import ResourceRecommendation, BuddyRecommendation
from app.models.concept import Concept
from app.models.skill import Skill
from app.models.resource_knowledge import ResourceKnowledge
from app.models.knowledge_knowledge import KnowledgeKnowledge
from app.models.concept_knowledge import ConceptKnowledge
from app.models.skill_knowledge import SkillKnowledge

__all__ = [
    "User",
    "Conversation",
    "Message",
    "UserProfile",
    "AgentExecutionLog",
    "Checkpoint",
    "MessageFeedback",
    "KnowledgePoint",
    "LearningResource",
    "LearnerResourceInteraction",
    "LearnerKnowledgeInteraction",
    "LearnerLearnerRelation",
    "ResourceRecommendation",
    "BuddyRecommendation",
    "Concept",
    "Skill",
    "ResourceKnowledge",
    "KnowledgeKnowledge",
    "ConceptKnowledge",
    "SkillKnowledge",
]
