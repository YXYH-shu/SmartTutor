"""Minimal adapter for resource and study-buddy recommendations."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.services.agents import get_agent

RESOURCE_SCENARIO = "resourceRecommendation"
STUDY_BUDDY_SCENARIO = "studyBuddyRecommendation"
_RECOMMENDATION_LIMIT = 5

logger = logging.getLogger(__name__)


class RecommendationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _required(data: dict[str, Any], key: str, location: str) -> Any:
    value = data.get(key)
    if value is None:
        raise RecommendationError("200001", f"{location}.{key} 缺失")
    return value


def _optional_text(value: Any, location: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or not value.strip():
        raise RecommendationError("200002", f"{location} 必须是非空字符串")
    return value.strip()


def _interaction_context(data: dict[str, Any]) -> dict[str, Any]:
    raw = data.get("interactionContext")
    if raw is None:
        return {
            "query": "",
            "draftAnswer": "",
            "history": [],
            "resourceIds": [],
            "userIds": [],
        }
    if not isinstance(raw, dict):
        raise RecommendationError("200002", "data.interactionContext 必须是对象")

    history = raw.get("history")
    if history is None:
        history = []
    if not isinstance(history, list):
        raise RecommendationError("200002", "data.interactionContext.history 必须是数组")

    messages: list[dict[str, str]] = []
    resource_ids: list[str] = []
    user_ids: list[str] = []
    for index, item in enumerate(history):
        location = f"data.interactionContext.history.{index}"
        if isinstance(item, str):
            messages.append({"role": "", "content": _optional_text(item, location)})
            continue
        if not isinstance(item, dict):
            raise RecommendationError("200002", f"{location} 必须是对象或字符串")

        role = item.get("role")
        if role is None:
            role = ""
        elif not isinstance(role, str):
            raise RecommendationError("200002", f"{location}.role 必须是字符串")
        for field, values in (("resourceId", resource_ids), ("userId", user_ids)):
            identifier = item.get(field)
            if identifier is not None:
                values.append(_optional_text(identifier, f"{location}.{field}"))
        for field in ("content", "text", "query", "draftAnswer"):
            if item.get(field) is not None:
                messages.append(
                    {"role": str(role), "content": _optional_text(item[field], f"{location}.{field}")}
                )
                break

    return {
        "query": _optional_text(raw.get("query"), "data.interactionContext.query"),
        "draftAnswer": _optional_text(
            raw.get("draftAnswer"), "data.interactionContext.draftAnswer"
        ),
        "history": messages,
        "resourceIds": list(dict.fromkeys(resource_ids)),
        "userIds": list(dict.fromkeys(user_ids)),
    }


def _request_context(
    data: dict[str, Any],
) -> tuple[str, dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    scenario = _optional_text(
        _required(data, "scenarioCode", "data"), "data.scenarioCode"
    )
    if scenario not in {RESOURCE_SCENARIO, STUDY_BUDDY_SCENARIO}:
        raise RecommendationError("200002", "data.scenarioCode 不支持")

    user_context = _required(data, "userContext", "data")
    evidence = _required(data, "learningEvidence", "data")
    if not isinstance(user_context, dict) or not isinstance(evidence, list):
        raise RecommendationError("200002", "data.userContext 必须是对象，data.learningEvidence 必须是数组")
    user_context = dict(user_context)
    for key in ("stage", "grade", "subject", "learnerStateSummary"):
        if user_context.get(key) is None:
            raise RecommendationError("200001", f"data.userContext.{key} 缺失")
        user_context[key] = _optional_text(user_context[key], f"data.userContext.{key}")
    if not evidence:
        raise RecommendationError("200002", "data.learningEvidence 必须是非空数组")
    normalized_evidence = []
    for index, item in enumerate(evidence):
        location = f"data.learningEvidence.{index}"
        if not isinstance(item, dict):
            raise RecommendationError("200002", f"{location} 必须是对象")
        knowledge_point_id = _required(item, "knowledgePointId", location)
        _required(item, "responseResult", location)
        occurred_at = _required(item, "occurredAt", location)
        normalized_evidence.append(
            {
                **item,
                "knowledgePointId": _optional_text(knowledge_point_id, f"{location}.knowledgePointId"),
                "occurredAt": _optional_text(occurred_at, f"{location}.occurredAt"),
            }
        )
    return scenario, user_context, normalized_evidence, _interaction_context(data)


def _candidate_resource_ids(data: dict[str, Any]) -> list[str]:
    candidates = data.get("candidateResources")
    if candidates is None:
        return []
    if not isinstance(candidates, list):
        raise RecommendationError("200002", "data.candidateResources 必须是数组")
    resource_ids = []
    for index, item in enumerate(candidates):
        location = f"data.candidateResources.{index}"
        if not isinstance(item, dict):
            raise RecommendationError("200002", f"{location} 必须是对象")
        resource_id = _required(item, "resourceId", location)
        resource_ids.append(_optional_text(resource_id, f"{location}.resourceId"))
    return list(dict.fromkeys(resource_ids))


def _candidate_user_ids(data: dict[str, Any]) -> list[str]:
    candidates = data.get("candidateUsers")
    if candidates is None:
        return []
    if not isinstance(candidates, list):
        raise RecommendationError("200002", "data.candidateUsers 必须是数组")
    user_ids = []
    for index, item in enumerate(candidates):
        location = f"data.candidateUsers.{index}"
        if not isinstance(item, dict):
            raise RecommendationError("200002", f"{location} 必须是对象")
        user_id = _required(item, "userId", location)
        user_ids.append(_optional_text(user_id, f"{location}.userId"))
    return list(dict.fromkeys(user_ids))


def _result(user_context: dict[str, Any], capability_version: str) -> dict[str, Any]:
    return {
        "decision": {"action": "pass", "reason": "已完成推荐排序。"},
        "learnerState": {"masterySummary": user_context["learnerStateSummary"]},
        "recommendations": [],
        "trace": {
            "traceId": uuid.uuid4().hex,
            "capabilityVersion": capability_version,
            "processedAt": datetime.now(timezone.utc).isoformat(),
        },
    }


def _ranking_input(
    user_id: str,
    user_context: dict[str, Any],
    evidence: list[dict[str, Any]],
    interaction: dict[str, Any],
) -> dict[str, Any]:
    knowledge_points = [str(item["knowledgePointId"]) for item in evidence]
    recent_messages = list(interaction["history"])
    if interaction["draftAnswer"]:
        recent_messages.append({"role": "assistant", "content": interaction["draftAnswer"]})
    return {
        "user_id": user_id,
        "current_message": interaction["query"] or f"{user_context['subject']}学习支持",
        "topic": interaction["query"] or user_context["subject"],
        "target_knowledge": knowledge_points,
        "weak_points": knowledge_points,
        "draft_answer": interaction["draftAnswer"],
        "recent_messages": recent_messages,
        "history_resource_ids": interaction["resourceIds"],
        "history_user_ids": interaction["userIds"],
    }


async def _recommend_resources(
    data: dict[str, Any],
    user_id: str,
    user_context: dict[str, Any],
    evidence: list[dict[str, Any]],
    interaction: dict[str, Any],
) -> dict[str, Any]:
    agent = get_agent("resource_recommender")
    candidate_resource_ids = _candidate_resource_ids(data)
    ranking_input = _ranking_input(user_id, user_context, evidence, interaction)
    if candidate_resource_ids:
        candidates = await agent._rows_to_resource_candidates(
            [{"resource_id": resource_id} for resource_id in candidate_resource_ids]
        )
        candidates_by_id = {str(item.get("id")): item for item in candidates}
        missing_ids = [
            resource_id
            for resource_id in candidate_resource_ids
            if resource_id not in candidates_by_id
        ]
        if missing_ids:
            raise RecommendationError("400001", f"资源不存在: {', '.join(missing_ids)}")
        candidates = [candidates_by_id[resource_id] for resource_id in candidate_resource_ids]
        ranked, _, metadata = await agent._ranking_tool(
            {"schema": "personality", "num": _RECOMMENDATION_LIMIT},
            candidates,
            ranking_input,
            fallback_reason="external_candidates",
        )
        used_fallback = metadata.get("ranking_backend") == "deterministic_fallback"
    else:
        execution = await agent.execute(
            ranking_input,
            context={"persist_recommendation": False, "log_execution": False},
        )
        output = execution.get("output") if isinstance(execution, dict) else None
        if not isinstance(output, dict):
            raise ValueError("resource recommender returned an invalid output")
        ranked = [item for item in output.get("resources", []) if isinstance(item, dict)]
        ranking = output.get("execution_context", {}).get("ranking", {})
        used_fallback = ranking.get("ranking_backend") == "deterministic_fallback"
        candidates = ranked
    result = _result(user_context, str(getattr(agent, "version", "resource-recommender")))
    result["recommendations"] = [
        {
            "resourceId": str(item.get("id") or item.get("resource_id")),
            "reason": "基于当前学习证据和交互上下文完成排序。",
        }
        for item in ranked[:_RECOMMENDATION_LIMIT]
        if item.get("id") or item.get("resource_id")
    ]
    if used_fallback and candidates:
        result.update(
            {
                "degraded": True,
                "degradeReason": "graphRankingUnavailable",
                "availableResults": [item["resourceId"] for item in result["recommendations"]],
            }
        )
    return result


async def _recommend_study_buddies(
    data: dict[str, Any],
    user_id: str,
    user_context: dict[str, Any],
    evidence: list[dict[str, Any]],
    interaction: dict[str, Any],
) -> dict[str, Any]:
    agent = get_agent("study_buddy")
    candidate_user_ids = _candidate_user_ids(data)
    ranking_input = _ranking_input(user_id, user_context, evidence, interaction)
    if candidate_user_ids:
        candidates = await agent._fetch_buddy_details(candidate_user_ids)
        candidates_by_id = {str(item.get("user_id")): item for item in candidates}
        missing_ids = [
            candidate_user_id
            for candidate_user_id in candidate_user_ids
            if candidate_user_id not in candidates_by_id
        ]
        if missing_ids:
            raise RecommendationError("400001", f"学伴用户不存在或不可用: {', '.join(missing_ids)}")
        candidates = [
            candidates_by_id[candidate_user_id]
            for candidate_user_id in candidate_user_ids
            if candidate_user_id != user_id
        ]
        if candidates:
            ranked, _, metadata = await agent._ranking_tool(
                {"schema": "personality", "num": _RECOMMENDATION_LIMIT},
                candidates,
                ranking_input,
                fallback_reason="external_candidates",
            )
            used_fallback = metadata.get("ranking_backend") == "deterministic_fallback"
        else:
            ranked = []
            used_fallback = False
    else:
        execution = await agent.execute(
            ranking_input,
            context={"persist_recommendation": False, "log_execution": False},
        )
        output = execution.get("output") if isinstance(execution, dict) else None
        if not isinstance(output, dict):
            raise ValueError("study buddy recommender returned an invalid output")
        ranked = [item for item in output.get("buddies", []) if isinstance(item, dict)]
        ranking = output.get("execution_context", {}).get("ranking", {})
        used_fallback = ranking.get("ranking_backend") == "deterministic_fallback"
        candidates = ranked
    result = _result(user_context, str(getattr(agent, "version", "study-buddy")))
    result["ext"] = {
        STUDY_BUDDY_SCENARIO: {
            "buddies": [
                {
                    "userId": str(item["user_id"]),
                    "nickname": str(item.get("nickname") or "学习伙伴"),
                    "matchScore": item.get("complement_score") or item.get("graph_score"),
                    "reason": "基于当前学习证据和交互上下文完成排序。",
                }
                for item in (ranked or [])[:_RECOMMENDATION_LIMIT]
                if item.get("user_id")
            ]
        }
    }
    if used_fallback and candidates:
        result.update(
            {
                "degraded": True,
                "degradeReason": "graphRankingUnavailable",
                "availableResults": [
                    buddy["userId"]
                    for buddy in result["ext"][STUDY_BUDDY_SCENARIO]["buddies"]
                ],
            }
        )
    return result


async def handle_learning_support(data: dict[str, Any], user_id: str) -> dict[str, Any]:
    scenario, user_context, evidence, interaction = _request_context(data)
    try:
        if scenario == RESOURCE_SCENARIO:
            return await _recommend_resources(data, user_id, user_context, evidence, interaction)
        return await _recommend_study_buddies(
            data, user_id, user_context, evidence, interaction
        )
    except RecommendationError:
        raise
    except Exception as exc:
        logger.exception("learningSupport recommendation failed: %s", type(exc).__name__)
        result = _result(user_context, "learning-support")
        result.update({"degraded": True, "degradeReason": type(exc).__name__, "availableResults": []})
        return result
