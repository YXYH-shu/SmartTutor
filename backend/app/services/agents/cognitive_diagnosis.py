"""Cognitive Diagnosis Agent – knowledge mastery assessment.

Post-processes by updating the user's knowledge_graph and weak_points
in their UserProfile.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.user_profile import UserProfile
from app.services.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class CognitiveDiagnosisAgent(BaseAgent):
    config_file = "cognitive_diagnosis"

    async def post_process(self, output: dict, context: dict) -> None:
        """Update user profile with diagnosis results."""
        user_id = context.get("user_id")
        if not user_id:
            return

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
            profile = result.scalar_one_or_none()
            if not profile:
                logger.warning("UserProfile not found for user %s", user_id)
                return

            # Merge knowledge_states into knowledge_graph
            knowledge_states = output.get("knowledge_states", [])
            if knowledge_states:
                existing = profile.knowledge_graph or {}
                for ks in knowledge_states:
                    skill_id = ks.get("skill_id") or ks.get("skill_name", "")
                    prob = ks.get("probability_correct", 0)
                    existing[skill_id] = prob
                profile.knowledge_graph = existing

            # Update weak points
            weak = output.get("weak_points", [])
            if weak:
                profile.weak_points = weak

            profile.last_diagnosis = datetime.now(timezone.utc)
            session.add(profile)
            await session.commit()
            logger.info("Updated UserProfile for user %s after diagnosis", user_id)
