"""Bounded context projections for the final knowledge response prompt."""

from __future__ import annotations

import copy
from typing import Any

from app.services.lpp_integration import build_diagnosis_prompt_context


_QUESTION_FIELDS = (
    "question_id",
    "question_text",
    "question_type",
    "question_type_code",
    "difficulty",
    "grade",
    "options",
    "order",
)

_KNOWLEDGE_POINT_FIELDS = (
    "knowledge_point_id",
    "knowledge_point_name",
    "skill_id",
    "skill_name",
)


def build_response_diagnosis_context(
    diagnosis: dict[str, Any],
    max_states: int = 10,
) -> dict[str, Any]:
    """Keep the diagnosis facts needed to write a learner-facing summary."""
    projected = build_diagnosis_prompt_context(diagnosis, max_states=max_states)
    for field in (
        "topic_analysis",
        "cognitive_attribution",
        "kt_student_id",
    ):
        value = diagnosis.get(field)
        if value not in (None, "", [], {}):
            projected[field] = copy.deepcopy(value)
    return projected


def _project_question(question: dict[str, Any]) -> dict[str, Any]:
    projected = {
        field: copy.deepcopy(question[field])
        for field in _QUESTION_FIELDS
        if field in question
    }
    projected["knowledge_points"] = [
        {
            field: copy.deepcopy(point[field])
            for field in _KNOWLEDGE_POINT_FIELDS
            if field in point
        }
        for point in (question.get("knowledge_points") or [])
        if isinstance(point, dict)
    ]
    return projected


def build_response_learning_plan_context(
    learning_plan: dict[str, Any],
) -> dict[str, Any]:
    """Keep LPP explanations and the fixed P1-P5 questions without duplicates."""
    projected: dict[str, Any] = {}
    for field in (
        "planning_rationale",
        "total_estimated_time",
        "adaptive_rules",
        "risk_correction",
        "lpp_source",
        "lpp_student_id",
    ):
        value = learning_plan.get(field)
        if value not in (None, "", [], {}):
            projected[field] = copy.deepcopy(value)

    milestones = learning_plan.get("milestones") or []
    if isinstance(milestones, list):
        projected["milestones"] = copy.deepcopy(milestones[:5])

    triggers = learning_plan.get("path_adjustment_triggers") or {}
    if isinstance(triggers, dict):
        projected["path_adjustment_triggers"] = {
            field: copy.deepcopy(triggers[field])
            for field in ("accelerate", "remediate", "redirect")
            if triggers.get(field) not in (None, "", [], {})
        }

    questions = [
        question
        for question in (learning_plan.get("recommended_questions") or [])
        if isinstance(question, dict)
    ]
    questions.sort(key=lambda question: question.get("order", 999))
    projected["recommended_questions"] = [
        _project_question(question) for question in questions[:5]
    ]
    return projected


def build_response_profile_context(
    profile: dict[str, Any],
    diagnosis_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Keep learner attributes and a short list of weak-point names."""
    projected = {
        field: copy.deepcopy(profile[field])
        for field in ("current_level", "learning_style", "grade_level")
        if profile.get(field) not in (None, "")
    }

    priority_states = (diagnosis_context or {}).get("priority_states") or []
    weak_point_names = [
        str(state.get("skill_name") or state.get("skill_id"))
        for state in priority_states
        if isinstance(state, dict) and (state.get("skill_name") or state.get("skill_id"))
    ]
    if not weak_point_names:
        for item in (profile.get("weak_points") or [])[:10]:
            if isinstance(item, str) and item:
                weak_point_names.append(item)
            elif isinstance(item, dict):
                name = item.get("skill_name") or item.get("name") or item.get("skill_id")
                if name:
                    weak_point_names.append(str(name))
    if weak_point_names:
        projected["weak_points"] = weak_point_names[:10]
    return projected
