"""Knowledge Responder Agent – generates natural language responses from scratch."""

from __future__ import annotations

from app.services.agents.base_agent import BaseAgent
from app.services.response_context import (
    build_response_diagnosis_context,
    build_response_learning_plan_context,
    build_response_profile_context,
)


class KnowledgeResponderAgent(BaseAgent):
    config_file = "knowledge_responder"

    async def enrich_input(self, input_data: dict, context: dict) -> dict:
        """Project prior KT/LPP output to the subset used by the response prompt."""
        enriched = await super().enrich_input(input_data, context)

        diagnosis = enriched.get("diagnosis_result")
        if not isinstance(diagnosis, dict):
            diagnosis = enriched.get("cognitive_diagnosis")
        diagnosis_context = None
        if isinstance(diagnosis, dict):
            diagnosis_context = build_response_diagnosis_context(diagnosis)
            enriched["diagnosis_result"] = diagnosis_context

        learning_plan = enriched.get("learning_plan")
        if not isinstance(learning_plan, dict):
            learning_plan = enriched.get("learning_path")
        if isinstance(learning_plan, dict):
            enriched["learning_plan"] = build_response_learning_plan_context(
                learning_plan
            )

        profile = enriched.get("user_profile")
        if isinstance(profile, dict):
            enriched["user_profile"] = build_response_profile_context(
                profile,
                diagnosis_context,
            )

        for key in (
            "cognitive_diagnosis",
            "learning_path",
            "knowledge_states",
            "mastery_rates",
            "weak_points",
            "knowledge_graph",
            "user_graph",
            "kt_predictions",
            "kt_mastery_rates",
            "kt_weak_points",
            "_last_output",
        ):
            enriched.pop(key, None)
        return enriched
