"""Resource recommendation agent with SQL recall and graph ranking only."""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from datetime import date, datetime
from typing import Any

from jinja2 import BaseLoader, Environment, StrictUndefined
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.services.agents.base_agent import BaseAgent
from app.services.response_context import (
    build_response_diagnosis_context,
    build_response_profile_context,
)

logger = logging.getLogger(__name__)
_jinja_env = Environment(loader=BaseLoader(), undefined=StrictUndefined)
_jinja_env.policies["json.dumps_kwargs"] = {
    **_jinja_env.policies["json.dumps_kwargs"],
    "ensure_ascii": False,
}

_DEFAULT_RESULT_COUNT = 5
_MAX_RESULT_COUNT = 15
_DEFAULT_PLAN_TIMEOUT_SECONDS = 20.0
_BOUNDARY_MESSAGE = "该智能体仅处理学习资源推荐，请说明希望推荐的资源或学习目标。"
_ALLOWED_TOOL_NAMES = {"SqlRetrievalTool", "RankingTool"}
_ALLOWED_RANKING_SCHEMAS = {"personality", "similarity"}
_ALLOWED_SQL_TABLES = {"learning_resources", "resource_knowledge", "knowledge_points"}
_BLOCKED_SQL_KEYWORDS = {
    "alter",
    "attach",
    "create",
    "delete",
    "detach",
    "drop",
    "insert",
    "merge",
    "pragma",
    "replace",
    "truncate",
    "update",
}


class ResourceRecommenderAgent(BaseAgent):
    """Recommend learning resources through SQL candidate recall and ranking."""

    config_file = "resource_recommender"

    async def enrich_input(self, input_data: dict, context: dict) -> dict:
        """Remove verbose KT and profile payloads before any planning prompt."""
        enriched = await super().enrich_input(input_data, context)
        diagnosis = enriched.get("diagnosis_result")
        if not isinstance(diagnosis, dict):
            diagnosis = enriched.get("cognitive_diagnosis")
        diagnosis_context = None
        if isinstance(diagnosis, dict):
            diagnosis_context = build_response_diagnosis_context(diagnosis)
            enriched["diagnosis_result"] = diagnosis_context

        profile = enriched.get("user_profile")
        if isinstance(profile, dict):
            enriched["user_profile"] = build_response_profile_context(
                profile,
                diagnosis_context,
            )
        return enriched

    async def execute(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        trace_id = context.get("_trace_id") or input_data.get("_trace_id") or "no-trace"
        started_at = time.perf_counter()
        enriched = self._prepare_plan_input(input_data)
        usage: dict[str, Any] = {}

        logger.info("[resource_recommender] start trace=%s", trace_id)

        # Fast path: one LLM planning call followed by deterministic tool execution.
        # stage_executor writes this output to context["resource_recommender"], where
        # subsequent agents read resource_list/resources without requiring a summary call.
        try:
            plan_payload, plan_usage = await asyncio.wait_for(
                self._generate_plan(enriched),
                timeout=self._plan_timeout_seconds(),
            )
            self._merge_usage(usage, plan_usage)
            if not plan_payload:
                raise ValueError("empty_plan_response")
            if not isinstance(plan_payload.get("need_tool"), bool):
                raise ValueError("invalid_plan_schema")
            plan = self._parse_plan(plan_payload)
            if plan["need_tool"] and not self._has_ranking_call(plan):
                raise ValueError("missing_valid_ranking_tool")
        except TimeoutError:
            logger.warning("[resource_recommender] plan timed out; using full-catalog ranking fallback")
            plan = self._fallback_plan(enriched, reason="plan_timeout", error_type="TimeoutError")
        except Exception as exc:
            logger.warning(
                "[resource_recommender] plan failed (%s); using full-catalog ranking fallback",
                type(exc).__name__,
            )
            plan = self._fallback_plan(
                enriched,
                reason=self._plan_failure_reason(exc),
                error_type=type(exc).__name__,
            )
        tool_results = self._empty_tool_results()
        if plan["need_tool"]:
            enriched = await self.enrich_input(enriched, context)
            tool_results = await self._execute_tools(plan, enriched)
        output = self._plan_and_tool_output(plan, tool_results)

        # Legacy full workflow retained for later restoration:
        # is_enriched = False
        # plan_history: list[dict[str, Any]] = []
        # reflection_history: list[dict[str, Any]] = []
        # tool_results = self._empty_tool_results()
        # reflection_result: dict[str, Any] = {}
        # boundary_only = False
        # max_attempts = max(1, self._safe_int(self.config.get("max_reflection_attempts"), 2))
        #
        # while True:
        #     plan_payload, plan_usage = await self._generate_plan(enriched, reflection_result)
        #     self._merge_usage(usage, plan_usage)
        #     plan = self._parse_plan(plan_payload)
        #     plan_history.append(plan)
        #
        #     if not plan["need_tool"]:
        #         output = self._boundary_output(plan, plan_history, reflection_history)
        #         boundary_only = True
        #         break
        #
        #     if not is_enriched:
        #         enriched = await self.enrich_input(enriched, context)
        #         is_enriched = True
        #     tool_results = await self._execute_tools(plan, enriched)
        #     reflection_result, reflection_usage = await self._reflection(plan, tool_results, enriched)
        #     self._merge_usage(usage, reflection_usage)
        #     reflection_history.append(reflection_result)
        #     if reflection_result["passed"]:
        #         output, summary_usage = await self._summary(
        #             plan,
        #             tool_results,
        #             enriched,
        #             reflection_result,
        #             plan_history=plan_history,
        #             reflection_history=reflection_history,
        #         )
        #         self._merge_usage(usage, summary_usage)
        #         break
        #
        #     if len(reflection_history) >= max_attempts:
        #         reflection_result = self._force_pass_reflection(reflection_result)
        #         reflection_history[-1] = reflection_result
        #         output, summary_usage = await self._summary(
        #             plan,
        #             tool_results,
        #             enriched,
        #             reflection_result,
        #             plan_history=plan_history,
        #             reflection_history=reflection_history,
        #         )
        #         self._merge_usage(usage, summary_usage)
        #         break
        #
        # if not boundary_only and context.get("persist_recommendation", True):
        #     recommendation_id = await self._persist_recommendation(
        #         output, enriched, context, tool_results, plan_history, reflection_history
        #     )
        #     if recommendation_id:
        #         output["recommendation_id"] = recommendation_id
        #         output["resource_list"]["recommendation_id"] = recommendation_id
        #
        # elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        # if not boundary_only and context.get("log_execution", True):
        #     await self._log_execution(
        #         conversation_id=context.get("conversation_id", ""),
        #         input_payload={
        #             "input": enriched,
        #             "plan_history": plan_history,
        #             "reflection_history": reflection_history,
        #             "tool_results": tool_results,
        #         },
        #         output_payload=output,
        #         execution_time_ms=elapsed_ms,
        #         turn_id=context.get("turn_id"),
        #     )
        # await self.post_process(output, context)

        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info("[resource_recommender] done trace=%s latency_ms=%s", trace_id, elapsed_ms)
        return {"agent": self.name, "output": output, "usage": usage, "latency_ms": elapsed_ms}

    async def _generate_plan(
        self,
        input_data: dict[str, Any],
        reflection_result: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        prompt_data = dict(input_data)
        prompt_data["reflection_result"] = reflection_result or {}
        return await self._call_llm_json("plan", prompt_data)

    def _plan_timeout_seconds(self) -> float:
        try:
            value = float(self.config.get("plan_timeout_seconds", _DEFAULT_PLAN_TIMEOUT_SECONDS))
        except (TypeError, ValueError):
            value = _DEFAULT_PLAN_TIMEOUT_SECONDS
        return max(1.0, value)

    @staticmethod
    def _has_ranking_call(plan: dict[str, Any]) -> bool:
        return any(call.get("tool_name") == "RankingTool" for call in plan.get("tool_calls", []))

    def _fallback_plan(
        self,
        input_data: dict[str, Any],
        *,
        reason: str,
        error_type: str,
    ) -> dict[str, Any]:
        target_count = self._extract_requested_count(str(input_data.get("current_message") or ""))
        ranking_input: dict[str, Any] = {"schema": "personality"}
        if target_count is not None:
            ranking_input["num"] = target_count
        return {
            "need_tool": True,
            "thought": "规划模型不可用，跳过 SQL 召回并使用全量资源进行个性化排序。",
            "final_answer": "",
            "target_knowledge": [],
            "target_count": target_count or 0,
            "recall_strategy": "plan_fallback_full_catalog",
            "ranking_criteria": ["personality"],
            "tool_calls": [
                {
                    "tool_name": "RankingTool",
                    "input": ranking_input,
                    "purpose": "规划失败后对全量资源执行个性化排序",
                }
            ],
            "plan_fallback": {
                "applied": True,
                "reason": reason,
                "error_type": error_type,
            },
        }

    @staticmethod
    def _plan_failure_reason(exc: Exception) -> str:
        message = str(exc)
        if message in {"empty_plan_response", "invalid_plan_schema", "missing_valid_ranking_tool"}:
            return message
        return "plan_error"

    @staticmethod
    def _extract_requested_count(message: str) -> int | None:
        digit_match = re.search(r"(?<!\d)(\d{1,2})\s*(?:个|条|份|项|套)?", message)
        if digit_match:
            return min(max(int(digit_match.group(1)), 1), _MAX_RESULT_COUNT)
        chinese_match = re.search(r"([一二两三四五六七八九十])\s*(?:个|条|份|项|套)", message)
        if not chinese_match:
            return None
        values = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        return values[chinese_match.group(1)]

    async def _reflection(
        self,
        plan: dict[str, Any],
        tool_results: dict[str, Any],
        input_data: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        payload, usage = await self._call_llm_json(
            "reflection",
            {**input_data, "plan": plan, "tool_results": tool_results},
        )
        return self._apply_reflection_checks(self._parse_reflection(payload), plan, tool_results), usage

    async def _summary(
        self,
        plan: dict[str, Any],
        tool_results: dict[str, Any],
        input_data: dict[str, Any],
        reflection_result: dict[str, Any],
        *,
        plan_history: list[dict[str, Any]],
        reflection_history: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        payload, usage = await self._call_llm_json(
            "summary",
            {
                **input_data,
                "plan": plan,
                "tool_results": tool_results,
                "reflection_result": reflection_result,
            },
        )
        if not payload:
            payload = self._fallback_summary(plan, tool_results, reflection_result)
        if not payload.get("planning"):
            payload["planning"] = self._planning_from_plan(plan)
        if not payload.get("resources"):
            payload["resources"] = tool_results["ranked_resources"]
        if not payload.get("reflection"):
            payload["reflection"] = self._reflection_for_output(reflection_result)
        if not payload.get("tool_trace"):
            payload["tool_trace"] = tool_results["tool_trace"]
        payload["plan_history"] = plan_history
        payload["reflection_history"] = reflection_history
        return self._ensure_output_shape(payload), usage

    async def _persist_recommendation(
        self,
        output: dict[str, Any],
        input_data: dict[str, Any],
        context: dict[str, Any],
        tool_results: dict[str, Any],
        plan_history: list[dict[str, Any]],
        reflection_history: list[dict[str, Any]],
    ) -> str:
        resources = [dict(item) for item in output.get("resources", []) if isinstance(item, dict)]
        learner_id = str(context.get("user_id") or input_data.get("user_id") or "").strip()
        if not resources or not learner_id:
            return ""

        ranks = []
        for index, resource in enumerate(resources, start=1):
            rank = {
                "rank": index,
                "resource_id": resource.get("id", ""),
                "title": resource.get("title", ""),
                "recommend_reason": resource.get("recommend_reason", ""),
            }
            for key in ("graph_score", "similarity_score", "similarity_reference_id", "similarity_reference_title"):
                if resource.get(key) is not None:
                    rank[key] = resource[key]
            ranks.append(rank)

        try:
            from app.database import AsyncSessionLocal
            from app.models.recommendation import ResourceRecommendation

            async with AsyncSessionLocal() as session:
                recommendation_id = str(uuid.uuid4())
                session.add(
                    ResourceRecommendation(
                        id=recommendation_id,
                        session_id=str(context.get("conversation_id") or "").strip() or None,
                        learner_id=learner_id,
                        candidates={"resources": tool_results["candidates"]},
                        rec_num=len(resources),
                        labels={
                            "planning": output.get("planning", {}),
                            "reflection": output.get("reflection", {}),
                            "tool_trace": output.get("tool_trace", []),
                            "execution_context": tool_results.get("execution_context", {}),
                            "plan_history": plan_history,
                            "reflection_history": reflection_history,
                        },
                        kg_version=str(input_data["kg_version"]) if input_data.get("kg_version") is not None else None,
                        model_version=str(self.llm_config.get("model") or self.version),
                        rec_resources={"resources": resources},
                        rec_ranks={"resources": ranks},
                        feedback_score=None,
                    )
                )
                await session.commit()
                return recommendation_id
        except Exception as exc:
            logger.warning("[resource_recommender] persist recommendation failed: %s", exc)
            return ""

    async def _call_llm_json(self, stage: str, data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        result = await self.llm.chat_completion(
            prompt=self._render_stage_prompt(stage, data),
            system_prompt=None,
            model=self.llm_config.get("model"),
            temperature=self.llm_config.get("temperature", 0.2),
            max_tokens=self.llm_config.get("max_tokens"),
            response_format="json",
            thinking=self.llm_config.get("thinking", False),
        )
        content = result.get("content", {})
        return (content if isinstance(content, dict) else {}), result.get("usage", {})

    def _render_stage_prompt(self, stage: str, data: dict[str, Any]) -> str:
        template = self.config.get(f"{stage}_prompt_template") or (
            self.system_prompt_template if stage == "plan" else ""
        )
        if not template:
            raise ValueError(f"Missing prompt template for resource_recommender.{stage}")
        return _jinja_env.from_string(template).render(**data)

    async def _execute_tools(self, plan: dict[str, Any], input_data: dict[str, Any]) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        ranked_resources: list[dict[str, Any]] = []
        trace: list[dict[str, Any]] = []
        sql_called = False
        execution_context: dict[str, Any] = {
            "candidate_source": "sql",
            "sql_called": False,
            "sql_result_count": 0,
            "ranking": {},
        }
        plan_fallback = plan.get("plan_fallback")
        if isinstance(plan_fallback, dict) and plan_fallback.get("applied") is True:
            execution_context["plan_fallback"] = dict(plan_fallback)
            trace.append(
                {
                    "tool": "PlanFallback",
                    "status": "applied",
                    "reason": str(plan_fallback.get("reason") or "plan_error"),
                    "error_type": str(plan_fallback.get("error_type") or ""),
                    "count": 0,
                }
            )

        for call in plan["tool_calls"]:
            name = str(call["tool_name"])
            tool_input = call["input"]
            if name == "SqlRetrievalTool":
                sql_called = True
                result = await self._sql_retrieval_tool(tool_input)
                candidates = self._dedupe_resources([*candidates, *result])
                execution_context["sql_called"] = True
                execution_context["sql_result_count"] = len(candidates)
                trace.append({"tool": name, "status": "executed", "input": tool_input, "count": len(result)})
            elif name == "RankingTool":
                fallback_reason = "sql_not_called" if not sql_called else "sql_empty"
                result, candidates, metadata = await self._ranking_tool(
                    tool_input, candidates, input_data, fallback_reason=fallback_reason
                )
                ranked_resources = result
                execution_context["candidate_source"] = metadata["candidate_source"]
                execution_context["ranking"] = metadata
                if metadata.get("fallback_reason"):
                    trace.append(
                        {
                            "tool": "CandidateFallback",
                            "status": "applied",
                            "reason": metadata["fallback_reason"],
                            "count": metadata["candidate_count"],
                        }
                    )
                trace.append({"tool": name, "status": "executed", "input": tool_input, "count": len(result), **metadata})

        return {
            "candidates": candidates,
            "ranked_resources": ranked_resources,
            "tool_trace": trace,
            "execution_context": execution_context,
        }

    async def _sql_retrieval_tool(self, tool_input: dict[str, Any]) -> list[dict[str, Any]]:
        sql = self._extract_sql(tool_input)
        if not sql:
            return []
        try:
            return await self._rows_to_resource_candidates(await self._run_select_sql(sql))
        except (ValueError, SQLAlchemyError) as exc:
            logger.warning("[resource_recommender] SQL recall failed: %s", exc)
            return []

    async def _ranking_tool(
        self,
        tool_input: dict[str, Any],
        candidates: list[dict[str, Any]],
        input_data: dict[str, Any],
        *,
        fallback_reason: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        requested_schema = str(tool_input.get("schema") or "personality").strip().lower()
        if requested_schema not in _ALLOWED_RANKING_SCHEMAS:
            raise ValueError(f"unsupported resource ranking schema: {requested_schema}")
        schema = requested_schema
        limit = self._result_limit(tool_input.get("num"))
        metadata: dict[str, Any] = {
            "requested_schema": requested_schema,
            "effective_schema": schema,
            "requested_num": tool_input.get("num"),
            "effective_num": limit["value"],
            "num_policy": limit["policy"],
            "candidate_source": "sql",
            "candidate_count": len(candidates),
        }

        if schema == "similarity":
            if candidates:
                pairs = await self._rank_similarity_pairs(candidates, limit["value"])
                metadata["ranking_backend"] = "text_embedding"
                if pairs is None:
                    metadata["similarity_status"] = "unavailable"
                    return [], candidates, metadata
                return self._numbered(pairs, limit["value"]), candidates, metadata
            metadata.update(
                {
                    "effective_schema": "personality",
                    "fallback_reason": "missing_similarity_anchor",
                    "candidate_source": "full_catalog",
                }
            )
            candidates = await self._load_all_resource_candidates()
        elif not candidates:
            metadata.update({"fallback_reason": fallback_reason, "candidate_source": "full_catalog"})
            candidates = await self._load_all_resource_candidates()

        metadata["candidate_count"] = len(candidates)
        ranked = self._rank_with_graph(candidates, input_data)
        if ranked is None:
            metadata["ranking_backend"] = "deterministic_fallback"
            ranked = list(candidates)
        else:
            metadata["ranking_backend"] = "graph"
        return self._numbered(ranked, limit["value"]), candidates, metadata

    async def _rank_similarity_pairs(
        self,
        anchors: list[dict[str, Any]],
        limit: int,
    ) -> list[dict[str, Any]] | None:
        anchor_by_id = {
            self._row_resource_id(anchor): anchor
            for anchor in self._dedupe_resources(anchors)
            if self._row_resource_id(anchor)
        }
        if not anchor_by_id:
            return None
        try:
            from algorithm.graph_recommender import get_graph_recommender

            pairs = get_graph_recommender().rank_resource_similarity_pairs(list(anchor_by_id), limit)
        except Exception as exc:
            logger.warning("[resource_recommender] resource similarity unavailable: %s", exc)
            return None
        if not pairs:
            return None

        details = await self._fetch_resource_details(self._unique_ids([pair.id for pair in pairs]))
        results: list[dict[str, Any]] = []
        for pair in pairs:
            detail = details.get(pair.id)
            anchor = anchor_by_id.get(pair.reference_id)
            if not detail or not anchor:
                continue
            candidate = self._resource_row_to_candidate(detail)
            candidate.update(
                {
                    "similarity_score": self._safe_float(pair.score, 0),
                    "similarity_reference_id": pair.reference_id,
                    "similarity_reference_title": str(anchor.get("title") or anchor.get("name") or pair.reference_id),
                    "recommend_reason": "Based on similarity to the selected reference resource.",
                }
            )
            results.append(candidate)
        return results or None

    def _rank_with_graph(
        self,
        candidates: list[dict[str, Any]],
        input_data: dict[str, Any],
    ) -> list[dict[str, Any]] | None:
        learner_id = str(input_data.get("user_id") or input_data.get("learner_id") or "").strip()
        candidate_by_id = {
            self._row_resource_id(candidate): candidate
            for candidate in candidates
            if self._row_resource_id(candidate)
        }
        if not learner_id or not candidate_by_id:
            return None
        try:
            from algorithm.graph_recommender import get_graph_recommender

            history_resource_ids = input_data.get("history_resource_ids")
            rank_kwargs: dict[str, Any] = {}
            if isinstance(history_resource_ids, (list, tuple, set)):
                history_resource_ids = [
                    resource_id.strip()
                    for resource_id in history_resource_ids
                    if isinstance(resource_id, str) and resource_id.strip()
                ]
                if history_resource_ids:
                    rank_kwargs["history_resource_ids"] = history_resource_ids
            scores = get_graph_recommender().rank_resources(
                learner_id,
                list(candidate_by_id),
                k=len(candidate_by_id),
                **rank_kwargs,
            )
        except Exception as exc:
            logger.warning("[resource_recommender] graph ranking unavailable: %s", exc)
            return None
        return [{**candidate_by_id[item.id], "graph_score": self._safe_float(item.score, 0)} for item in scores if item.id in candidate_by_id]

    async def _load_all_resource_candidates(self) -> list[dict[str, Any]]:
        from app.database import AsyncSessionLocal
        from app.models.learning_resource import LearningResource

        async with AsyncSessionLocal() as session:
            result = await session.execute(select(LearningResource.id).order_by(LearningResource.name, LearningResource.id))
            rows = [{"id": str(resource_id)} for resource_id in result.scalars().all()]
        return await self._rows_to_resource_candidates(rows)

    def _result_limit(self, raw_value: Any) -> dict[str, Any]:
        if raw_value is None or str(raw_value).strip() == "":
            return {"value": _DEFAULT_RESULT_COUNT, "policy": "default"}
        value = self._safe_int(raw_value, 0)
        if value <= 0:
            return {"value": _DEFAULT_RESULT_COUNT, "policy": "default_invalid"}
        if value > _MAX_RESULT_COUNT:
            return {"value": _MAX_RESULT_COUNT, "policy": "capped"}
        return {"value": value, "policy": "requested"}

    @staticmethod
    def _numbered(resources: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        return [{**resource, "rank": index} for index, resource in enumerate(resources[:limit], start=1)]

    def _parse_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        calls = payload.get("tool_calls") if isinstance(payload.get("tool_calls"), list) else []
        tool_calls: list[dict[str, Any]] = []
        for call in calls:
            if not isinstance(call, dict):
                continue
            tool_name = str(call.get("tool_name") or "").strip()
            if tool_name not in _ALLOWED_TOOL_NAMES:
                continue
            tool_input = call.get("input") if isinstance(call.get("input"), dict) else {}
            if tool_name == "RankingTool":
                schema = str(tool_input.get("schema") or "personality").strip().lower()
                if schema not in _ALLOWED_RANKING_SCHEMAS:
                    continue
                tool_input = {**tool_input, "schema": schema}
            tool_calls.append(
                {
                    "tool_name": tool_name,
                    "input": tool_input,
                    "purpose": str(call.get("purpose") or ""),
                }
            )
        return {
            "need_tool": payload.get("need_tool") is True,
            "thought": str(payload.get("thought") or ""),
            "final_answer": str(payload.get("final_answer") or ""),
            "target_knowledge": self._as_list(payload.get("target_knowledge")),
            "target_count": self._safe_int(payload.get("target_count"), 0),
            "recall_strategy": str(payload.get("recall_strategy") or ""),
            "ranking_criteria": [
                value
                for value in self._as_list(payload.get("ranking_criteria"))
                if str(value).strip().lower() in _ALLOWED_RANKING_SCHEMAS
            ],
            "tool_calls": tool_calls,
        }

    def _parse_reflection(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "passed": payload.get("passed") is True,
            "issues": [str(item) for item in self._as_list(payload.get("issues")) if item],
            "suggestion": str(payload.get("suggestion") or payload.get("improvement_suggestion") or ""),
            "coverage_score": self._safe_float(payload.get("coverage_score"), 0),
            "difficulty_match": self._safe_float(payload.get("difficulty_match"), 0),
            "diversity_score": self._safe_float(payload.get("diversity_score"), 0),
        }

    def _apply_reflection_checks(
        self,
        reflection: dict[str, Any],
        plan: dict[str, Any],
        tool_results: dict[str, Any],
    ) -> dict[str, Any]:
        names = {call["tool_name"] for call in plan["tool_calls"]}
        ranking = tool_results.get("execution_context", {}).get("ranking", {})
        ranked_count = len(tool_results.get("ranked_resources", []))
        expected_count = min(
            self._safe_int(ranking.get("effective_num"), _DEFAULT_RESULT_COUNT),
            self._safe_int(ranking.get("candidate_count"), 0) or ranked_count,
        )
        issues = list(reflection["issues"])
        if "RankingTool" not in names:
            issues.append("推荐计划缺少 RankingTool。")
        elif ranked_count == 0:
            issues.append("排序后没有可用资源。")
        elif ranked_count < expected_count:
            issues.append(f"有效目标数量为 {expected_count}，当前仅返回 {ranked_count} 条。")
        if issues:
            reflection["passed"] = False
            reflection["issues"] = list(dict.fromkeys(issues))
            reflection["coverage_score"] = min(reflection["coverage_score"], 0.5)
        return reflection

    def _extract_sql(self, tool_input: dict[str, Any]) -> str:
        return str(tool_input.get("sql") or tool_input.get("query") or "").strip()

    async def _run_select_sql(self, sql: str) -> list[dict[str, Any]]:
        safe_sql = self._validate_select_sql(sql)
        from app.database import AsyncSessionLocal, engine

        async with AsyncSessionLocal() as session:
            if engine.dialect.name == "sqlite":
                await session.execute(text("PRAGMA query_only = ON"))
            elif engine.dialect.name == "mysql":
                await session.execute(text("SET SESSION TRANSACTION READ ONLY"))
            try:
                result = await session.execute(text(safe_sql))
                return [self._serialize_row(dict(row)) for row in result.mappings().all()]
            finally:
                if engine.dialect.name == "sqlite":
                    await session.execute(text("PRAGMA query_only = OFF"))
                elif engine.dialect.name == "mysql":
                    await session.execute(text("SET SESSION TRANSACTION READ WRITE"))

    def _validate_select_sql(self, sql: str) -> str:
        normalized = sql.strip().rstrip(";").strip()
        if not normalized or ";" in normalized or "--" in normalized or "/*" in normalized or "*/" in normalized:
            raise ValueError("invalid SQL statement")
        compact = re.sub(r"\s+", " ", normalized).lower()
        if not compact.startswith("select "):
            raise ValueError("only SELECT statements are allowed")
        if any(re.search(rf"\b{keyword}\b", compact) for keyword in _BLOCKED_SQL_KEYWORDS):
            raise ValueError("blocked SQL keyword")
        tables = self._extract_sql_tables(compact)
        if not tables or tables - _ALLOWED_SQL_TABLES:
            raise ValueError("SQL references an unsupported table")
        return normalized

    @staticmethod
    def _extract_sql_tables(sql: str) -> set[str]:
        return {
            match.group(1).strip("`\"[]").split(".")[-1]
            for match in re.finditer(r"\b(?:from|join)\s+([`\"\[]?[\w.]+[`\"\]]?)", sql)
        }

    async def _rows_to_resource_candidates(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        resource_ids = self._unique_ids(self._row_resource_id(row) for row in rows)
        details = await self._fetch_resource_details(resource_ids)
        return [self._resource_row_to_candidate(details[resource_id]) for resource_id in resource_ids if resource_id in details]

    async def _fetch_resource_details(self, resource_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not resource_ids:
            return {}
        from app.database import AsyncSessionLocal
        from app.models.knowledge_point import KnowledgePoint
        from app.models.learning_resource import LearningResource
        from app.models.resource_knowledge import ResourceKnowledge

        async with AsyncSessionLocal() as session:
            detail_result = await session.execute(
                select(
                    LearningResource.id,
                    LearningResource.name,
                    LearningResource.content,
                    LearningResource.type,
                    LearningResource.url,
                    LearningResource.difficult,
                    LearningResource.time_need,
                ).where(LearningResource.id.in_(resource_ids))
            )
            details = {str(row["id"]): self._serialize_row(dict(row)) for row in detail_result.mappings().all()}
            tags = await session.execute(
                select(ResourceKnowledge.resource_id, KnowledgePoint.name.label("knowledge_name"))
                .join(KnowledgePoint, ResourceKnowledge.kp_id == KnowledgePoint.id)
                .where(ResourceKnowledge.resource_id.in_(resource_ids))
            )
            for row in tags.mappings().all():
                detail = details.get(str(row["resource_id"]))
                if detail and row["knowledge_name"]:
                    detail.setdefault("knowledge_tags", []).append(row["knowledge_name"])
        return {resource_id: details[resource_id] for resource_id in resource_ids if resource_id in details}

    def _resource_row_to_candidate(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": self._row_resource_id(row),
            "type": str(row.get("type") or "article"),
            "title": str(row.get("title") or row.get("name") or "Untitled resource"),
            "url": str(row.get("url") or ""),
            "difficulty": self._difficulty_label(row.get("difficulty") or row.get("difficult")),
            "time_needed_min": self._safe_int(row.get("time_needed_min") or row.get("time_need"), 0),
            "knowledge_tags": self._as_list(row.get("knowledge_tags") or row.get("tags")),
            "recommend_reason": str(row.get("recommend_reason") or "Selected by resource recall."),
        }

    @staticmethod
    def _row_resource_id(row: dict[str, Any]) -> str:
        return str(row.get("id") or row.get("resource_id") or row.get("learning_resource_id") or "")

    @staticmethod
    def _unique_ids(values: Any) -> list[str]:
        return list(dict.fromkeys(value for value in values if value))

    @staticmethod
    def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value.isoformat() if isinstance(value, datetime | date) else value
            for key, value in row.items()
        }

    def _difficulty_label(self, value: Any) -> str:
        try:
            score = float(value)
        except (TypeError, ValueError):
            return str(value) if value else "intermediate"
        return "beginner" if score <= 0.4 else "advanced" if score >= 0.7 else "intermediate"

    @staticmethod
    def _dedupe_resources(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_id = {str(item.get("id") or item.get("resource_id") or ""): item for item in resources if isinstance(item, dict)}
        return [item for resource_id, item in by_id.items() if resource_id]

    def _force_pass_reflection(self, reflection: dict[str, Any]) -> dict[str, Any]:
        return {**reflection, "passed": True, "forced_pass": True}

    def _fallback_summary(
        self,
        plan: dict[str, Any],
        tool_results: dict[str, Any],
        reflection: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "recommendation_text": "已根据当前学习需求完成资源推荐。",
            "planning": self._planning_from_plan(plan),
            "resources": tool_results["ranked_resources"],
            "rationale": plan["thought"],
            "sequence": [],
            "reflection": self._reflection_for_output(reflection),
            "tool_trace": tool_results["tool_trace"],
        }

    def _plan_and_tool_output(
        self,
        plan: dict[str, Any],
        tool_results: dict[str, Any],
    ) -> dict[str, Any]:
        """Expose deterministic recall/ranking results without more LLM calls."""
        recommendation_text = (
            "已完成资源检索与排序。"
            if plan["need_tool"]
            else plan["final_answer"] or _BOUNDARY_MESSAGE
        )
        return self._ensure_output_shape(
            {
                "recommendation_text": recommendation_text,
                "planning": self._planning_from_plan(plan),
                "resources": tool_results["ranked_resources"],
                "rationale": plan["thought"],
                "sequence": [],
                "reflection": {},
                "tool_trace": tool_results["tool_trace"],
                "execution_context": tool_results["execution_context"],
                "plan_history": [plan],
                "reflection_history": [],
            }
        )

    def _boundary_output(
        self,
        plan: dict[str, Any],
        plan_history: list[dict[str, Any]],
        reflection_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self._ensure_output_shape(
            {
                "recommendation_text": _BOUNDARY_MESSAGE,
                "planning": self._planning_from_plan(plan),
                "resources": [],
                "rationale": "recommendation_only_boundary",
                "sequence": [],
                "reflection": {"passed": True, "coverage_score": 1, "difficulty_match": 1, "diversity_score": 1},
                "tool_trace": [],
                "plan_history": plan_history,
                "reflection_history": reflection_history,
            }
        )

    @staticmethod
    def _planning_from_plan(plan: dict[str, Any]) -> dict[str, Any]:
        planning = {
            "recall_strategy": plan.get("recall_strategy", ""),
            "ranking_criteria": plan.get("ranking_criteria", []),
            "target_count": plan.get("target_count", 0),
        }
        if isinstance(plan.get("plan_fallback"), dict):
            planning["plan_fallback"] = dict(plan["plan_fallback"])
        return planning

    @staticmethod
    def _reflection_for_output(reflection: dict[str, Any]) -> dict[str, Any]:
        return {
            "coverage_score": reflection.get("coverage_score", 0),
            "difficulty_match": reflection.get("difficulty_match", 0),
            "diversity_score": reflection.get("diversity_score", 0),
            "improvement_suggestion": reflection.get("suggestion", ""),
            "passed": reflection.get("passed", False),
            "forced_pass": reflection.get("forced_pass", False),
        }

    @staticmethod
    def _empty_tool_results() -> dict[str, Any]:
        return {"candidates": [], "ranked_resources": [], "tool_trace": [], "execution_context": {}}

    @staticmethod
    def _prepare_plan_input(input_data: dict[str, Any]) -> dict[str, Any]:
        prepared = dict(input_data)
        diagnosis = prepared.get("diagnosis_result")
        if not isinstance(diagnosis, dict):
            diagnosis = prepared.get("cognitive_diagnosis")
        diagnosis_context = None
        if isinstance(diagnosis, dict):
            diagnosis_context = build_response_diagnosis_context(diagnosis)
            prepared["diagnosis_result"] = diagnosis_context

        profile = prepared.get("user_profile")
        if isinstance(profile, dict):
            prepared["user_profile"] = build_response_profile_context(
                profile,
                diagnosis_context,
            )
        prepared.setdefault("recent_messages", [])
        prepared.setdefault("current_message", prepared.get("message", ""))
        return prepared

    def _ensure_output_shape(self, output: dict[str, Any]) -> dict[str, Any]:
        resources = [self._normalize_resource(item) for item in output.get("resources", []) if isinstance(item, dict)]
        text_value = str(
            output.get("recommendation_text")
            or output.get("response_text")
            or output.get("content")
            or _BOUNDARY_MESSAGE
        )
        planning = output.get("planning") if isinstance(output.get("planning"), dict) else {}
        reflection = output.get("reflection") if isinstance(output.get("reflection"), dict) else {}
        trace = [item for item in output.get("tool_trace", []) if isinstance(item, dict)]
        execution_context = (
            output.get("execution_context")
            if isinstance(output.get("execution_context"), dict)
            else {}
        )
        resource_list = {
            "resources": resources,
            "planning": planning,
            "rationale": str(output.get("rationale") or ""),
            "sequence": self._as_list(output.get("sequence")),
            "tool_trace": trace,
            "execution_context": execution_context,
        }
        return {
            "recommendation_text": text_value,
            "response_text": str(output.get("response_text") or text_value),
            "content": str(output.get("content") or text_value),
            "raw_response": str(output.get("raw_response") or text_value),
            "final_response": str(output.get("final_response") or text_value),
            "resource_list": resource_list,
            "planning": planning,
            "resources": resources,
            "rationale": resource_list["rationale"],
            "sequence": resource_list["sequence"],
            "reflection": reflection,
            "tool_trace": trace,
            "execution_context": execution_context,
            "plan_history": [item for item in output.get("plan_history", []) if isinstance(item, dict)],
            "reflection_history": [item for item in output.get("reflection_history", []) if isinstance(item, dict)],
        }

    def _normalize_resource(self, item: dict[str, Any]) -> dict[str, Any]:
        resource = self._resource_row_to_candidate(item)
        for key in (
            "rank",
            "graph_score",
            "similarity_score",
            "similarity_reference_id",
            "similarity_reference_title",
        ):
            if item.get(key) is not None:
                resource[key] = item[key]
        return resource

    @staticmethod
    def _safe_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _as_list(value: Any) -> list[Any]:
        if value is None:
            return []
        return value if isinstance(value, list) else list(value) if isinstance(value, (tuple, set)) else [value]

    @staticmethod
    def _count_tool_result(value: Any) -> int:
        return len(value) if isinstance(value, (list, tuple, set, dict)) else int(value is not None)

    @staticmethod
    def _merge_usage(total: dict[str, Any], usage: dict[str, Any]) -> None:
        for key, value in usage.items():
            total[key] = total.get(key, 0) + value if isinstance(value, int | float) else value
