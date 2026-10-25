"""Study-buddy recommendation with SQL recall and graph ranking only."""

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

logger = logging.getLogger(__name__)
_jinja_env = Environment(loader=BaseLoader(), undefined=StrictUndefined)
_jinja_env.policies["json.dumps_kwargs"] = {
    **_jinja_env.policies["json.dumps_kwargs"],
    "ensure_ascii": False,
}

_DEFAULT_RESULT_COUNT = 5
_MAX_RESULT_COUNT = 15
_DEFAULT_PLAN_TIMEOUT_SECONDS = 20.0
_BOUNDARY_MESSAGE = "该智能体仅处理学习伙伴推荐，请说明希望寻找的学习伙伴或共同学习目标。"
_ALLOWED_TOOL_NAMES = {"SqlRetrievalTool", "RankingTool"}
_ALLOWED_RANKING_SCHEMAS = {"personality", "similarity"}
_ALLOWED_SQL_TABLES = {
    "users",
    "user_profiles",
    "learner_knowledge_interactions",
    "knowledge_points",
}
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


class StudyBuddyAgent(BaseAgent):
    """Recommend study partners through SQL candidate recall and graph ranking."""

    config_file = "study_buddy"

    async def execute(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        trace_id = context.get("_trace_id") or input_data.get("_trace_id") or "no-trace"
        started_at = time.perf_counter()
        enriched = self._prepare_plan_input(input_data, context)
        usage: dict[str, Any] = {}

        logger.info("[study_buddy] start trace=%s", trace_id)

        # Fast path: one LLM planning call followed by deterministic tool execution.
        # stage_executor writes this output to context["study_buddy"], where
        # subsequent agents read buddy_list/buddies without a summary call.
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
            logger.warning("[study_buddy] plan timed out; using full-catalog ranking fallback")
            plan = self._fallback_plan(enriched, reason="plan_timeout", error_type="TimeoutError")
        except Exception as exc:
            logger.warning(
                "[study_buddy] plan failed (%s); using full-catalog ranking fallback",
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
        # boundary_only = False
        # plan_history: list[dict[str, Any]] = []
        # reflection_history: list[dict[str, Any]] = []
        # tool_results = self._empty_tool_results()
        # reflection_result: dict[str, Any] = {}
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
        #
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
        #         output["buddy_list"]["recommendation_id"] = recommendation_id
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
        logger.info("[study_buddy] done trace=%s latency_ms=%s", trace_id, elapsed_ms)
        return {"agent": self.name, "output": output, "usage": usage, "latency_ms": elapsed_ms}

    async def enrich_input(self, input_data: dict, context: dict) -> dict:
        if not input_data.get("user_id") and context.get("user_id"):
            input_data["user_id"] = str(context["user_id"])
        enriched = await super().enrich_input(input_data, context)
        profile = enriched.get("user_profile") if isinstance(enriched.get("user_profile"), dict) else {}
        diagnosis = enriched.get("diagnosis_result") if isinstance(enriched.get("diagnosis_result"), dict) else {}
        enriched.setdefault("topic", enriched.get("current_message", ""))
        enriched.setdefault("user_graph", profile.get("knowledge_graph", {}))
        enriched.setdefault("preferences", profile.get("preferences", {}))
        enriched.setdefault("learning_style", profile.get("learning_style"))
        enriched.setdefault("current_level", profile.get("current_level"))
        enriched.setdefault("grade_level", profile.get("grade_level"))
        enriched.setdefault("weak_points", profile.get("weak_points") or diagnosis.get("weak_points") or [])
        return enriched

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
            "thought": "规划模型不可用，跳过 SQL 召回并使用全量活跃学习者进行个性化排序。",
            "final_answer": "",
            "target_count": target_count or 0,
            "recall_strategy": "plan_fallback_full_catalog",
            "ranking_criteria": ["personality"],
            "tool_calls": [
                {
                    "tool_name": "RankingTool",
                    "input": ranking_input,
                    "purpose": "规划失败后对全量活跃学习者执行个性化排序",
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
        digit_match = re.search(r"(?<!\d)(\d{1,2})\s*(?:个|位|名|组)?", message)
        if digit_match:
            return min(max(int(digit_match.group(1)), 1), _MAX_RESULT_COUNT)
        chinese_match = re.search(r"([一二两三四五六七八九十])\s*(?:个|位|名|组)", message)
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
        if not payload.get("buddies"):
            payload["buddies"] = tool_results["ranked_buddies"]
        if not payload.get("reflection"):
            payload["reflection"] = self._reflection_for_output(reflection_result)
        if not payload.get("tool_trace"):
            payload["tool_trace"] = tool_results["tool_trace"]
        payload["plan_history"] = plan_history
        payload["reflection_history"] = reflection_history
        return self._ensure_output_shape(payload, tool_results, plan, reflection_result), usage

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
            raise ValueError(f"Missing prompt template for study_buddy.{stage}")
        return _jinja_env.from_string(template).render(**data)

    async def _execute_tools(self, plan: dict[str, Any], input_data: dict[str, Any]) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        ranked_buddies: list[dict[str, Any]] = []
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
                candidates = self._dedupe_buddies([*candidates, *result])
                execution_context["sql_called"] = True
                execution_context["sql_result_count"] = len(candidates)
                trace.append({"tool": name, "status": "executed", "input": tool_input, "count": len(result)})
            elif name == "RankingTool":
                fallback_reason = "sql_not_called" if not sql_called else "sql_empty"
                result, candidates, metadata = await self._ranking_tool(
                    tool_input, candidates, input_data, fallback_reason=fallback_reason
                )
                ranked_buddies = result
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
            "ranked_buddies": ranked_buddies,
            "tool_trace": trace,
            "execution_context": execution_context,
        }

    async def _sql_retrieval_tool(self, tool_input: dict[str, Any]) -> list[dict[str, Any]]:
        sql = self._extract_sql(tool_input)
        if not sql:
            return []
        try:
            return await self._rows_to_buddy_candidates(await self._run_select_sql(sql))
        except (ValueError, SQLAlchemyError) as exc:
            logger.warning("[study_buddy] SQL recall failed: %s", exc)
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
            raise ValueError(f"unsupported study-buddy ranking schema: {requested_schema}")
        limit = self._result_limit(tool_input.get("num"))
        candidates = [
            candidate
            for candidate in self._dedupe_buddies(candidates)
            if str(candidate.get("user_id") or "") != self._learner_id(input_data)
        ]
        metadata: dict[str, Any] = {
            "requested_schema": requested_schema,
            "effective_schema": requested_schema,
            "requested_num": tool_input.get("num"),
            "effective_num": limit["value"],
            "num_policy": limit["policy"],
            "candidate_source": "sql",
            "candidate_count": len(candidates),
        }
        if not candidates:
            metadata.update({"fallback_reason": fallback_reason, "candidate_source": "full_catalog"})
            candidates = await self._load_all_buddy_candidates(self._learner_id(input_data))

        metadata["candidate_count"] = len(candidates)
        ranked = (
            self._rank_with_graph(candidates, input_data)
            if requested_schema == "personality"
            else self._similarity_with_graph(candidates, input_data)
        )
        if ranked is None:
            metadata["ranking_backend"] = "deterministic_fallback"
            ranked = list(candidates)
        else:
            metadata["ranking_backend"] = "graph" if requested_schema == "personality" else "graph_similarity"
        metadata["eligible_candidate_count"] = len(ranked)
        return self._numbered(ranked, limit["value"]), candidates, metadata

    def _rank_with_graph(
        self,
        candidates: list[dict[str, Any]],
        input_data: dict[str, Any],
    ) -> list[dict[str, Any]] | None:
        learner_id = self._learner_id(input_data)
        candidate_by_id = {str(item.get("user_id")): item for item in candidates if item.get("user_id")}
        if not learner_id or not candidate_by_id:
            return None
        try:
            from algorithm.graph_recommender import get_graph_recommender

            history_user_ids = input_data.get("history_user_ids")
            rank_kwargs: dict[str, Any] = {}
            if isinstance(history_user_ids, (list, tuple, set)):
                history_user_ids = [
                    user_id.strip()
                    for user_id in history_user_ids
                    if isinstance(user_id, str) and user_id.strip()
                ]
                if history_user_ids:
                    rank_kwargs["history_partner_ids"] = history_user_ids
            scores = get_graph_recommender().rank_peers(
                learner_id,
                list(candidate_by_id),
                k=len(candidate_by_id),
                **rank_kwargs,
            )
        except Exception as exc:
            logger.warning("[study_buddy] graph ranking unavailable: %s", exc)
            return None
        return [
            self._decorate_buddy(candidate_by_id[item.id], graph_score=self._safe_float(item.score, 0))
            for item in scores
            if item.id in candidate_by_id
        ]

    def _similarity_with_graph(
        self,
        candidates: list[dict[str, Any]],
        input_data: dict[str, Any],
    ) -> list[dict[str, Any]] | None:
        learner_id = self._learner_id(input_data)
        candidate_by_id = {str(item.get("user_id")): item for item in candidates if item.get("user_id")}
        if not learner_id or not candidate_by_id:
            return None
        try:
            from algorithm.graph_recommender import get_graph_recommender

            history_user_ids = input_data.get("history_user_ids")
            rank_kwargs: dict[str, Any] = {}
            if isinstance(history_user_ids, (list, tuple, set)):
                history_user_ids = [
                    user_id.strip()
                    for user_id in history_user_ids
                    if isinstance(user_id, str) and user_id.strip()
                ]
                if history_user_ids:
                    rank_kwargs["history_partner_ids"] = history_user_ids
            scores = get_graph_recommender().similar_peers(
                learner_id,
                list(candidate_by_id),
                k=len(candidate_by_id),
                **rank_kwargs,
            )
        except Exception as exc:
            logger.warning("[study_buddy] graph similarity unavailable: %s", exc)
            return None
        return [
            self._decorate_buddy(
                candidate_by_id[item.id],
                similarity_score=self._safe_float(item.score, 0),
                complement_score=(self._safe_float(item.score, 0) + 1.0) / 2.0,
                dimension_scores={"graph_embedding_similarity": self._safe_float(item.score, 0)},
            )
            for item in scores
            if item.id in candidate_by_id
        ]

    async def _load_all_buddy_candidates(self, learner_id: str) -> list[dict[str, Any]]:
        from app.database import AsyncSessionLocal
        from app.models.user import User

        async with AsyncSessionLocal() as session:
            statement = select(User.id).where(User.is_active.is_(True)).order_by(User.created_at, User.id)
            if learner_id:
                statement = statement.where(User.id != learner_id)
            resource_ids = [str(user_id) for user_id in (await session.execute(statement)).scalars().all()]
        return await self._fetch_buddy_details(resource_ids)

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
    def _numbered(buddies: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        return [{**buddy, "rank": index} for index, buddy in enumerate(buddies[:limit], start=1)]

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
            "compatibility_score": self._safe_float(payload.get("compatibility_score"), 0),
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
        ranked_count = len(tool_results.get("ranked_buddies", []))
        expected_count = min(
            self._safe_int(ranking.get("effective_num"), _DEFAULT_RESULT_COUNT),
            self._safe_int(ranking.get("eligible_candidate_count"), 0) or ranked_count,
        )
        issues = list(reflection["issues"])
        if "RankingTool" not in names:
            issues.append("推荐计划缺少 RankingTool。")
        elif ranked_count == 0:
            issues.append("排序后没有可用学伴。")
        elif ranked_count < expected_count:
            issues.append(f"有效目标数量为 {expected_count}，当前仅返回 {ranked_count} 位学伴。")
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

    async def _rows_to_buddy_candidates(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        learner_ids = self._unique_ids(self._row_learner_id(row) for row in rows)
        return await self._fetch_buddy_details(learner_ids)

    async def _fetch_buddy_details(self, learner_ids: list[str]) -> list[dict[str, Any]]:
        if not learner_ids:
            return []
        from app.database import AsyncSessionLocal
        from app.models.user import User
        from app.models.user_profile import UserProfile

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(
                    User.id.label("user_id"),
                    User.username,
                    UserProfile.current_level,
                    UserProfile.learning_style,
                    UserProfile.grade_level,
                    UserProfile.weak_points,
                    UserProfile.knowledge_graph,
                )
                .outerjoin(UserProfile, UserProfile.user_id == User.id)
                .where(User.id.in_(learner_ids), User.is_active.is_(True))
            )
            details = {
                str(row["user_id"]): self._candidate_from_row(self._serialize_row(dict(row)))
                for row in result.mappings().all()
            }
        return [details[learner_id] for learner_id in learner_ids if learner_id in details]

    @staticmethod
    def _candidate_from_row(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "user_id": str(row.get("user_id") or row.get("id") or ""),
            "nickname": str(row.get("nickname") or row.get("username") or "学习伙伴"),
            "current_level": row.get("current_level"),
            "learning_style": row.get("learning_style"),
            "grade_level": row.get("grade_level"),
            "weak_points": row.get("weak_points") or [],
            "knowledge_graph": row.get("knowledge_graph") or {},
        }

    def _decorate_buddy(
        self,
        candidate: dict[str, Any],
        llm_value: dict[str, Any] | None = None,
        *,
        graph_score: float | None = None,
        similarity_score: float | None = None,
        complement_score: float | None = None,
        dimension_scores: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        llm_value = llm_value or {}
        effective_graph_score = graph_score if graph_score is not None else candidate.get("graph_score")
        effective_similarity_score = similarity_score if similarity_score is not None else candidate.get("similarity_score")
        score = complement_score
        if score is None:
            score = effective_graph_score
        if score is None and effective_similarity_score is not None:
            score = (self._safe_float(effective_similarity_score, 0) + 1.0) / 2.0
        if score is None:
            score = candidate.get("complement_score")
        result = {
            "user_id": str(candidate.get("user_id") or ""),
            "nickname": str(candidate.get("nickname") or "学习伙伴"),
            "complement_score": self._safe_float(score, 0),
            "dimension_scores": dimension_scores or candidate.get("dimension_scores") or llm_value.get("dimension_scores") or {},
            "strengths": self._strong_knowledge(candidate.get("knowledge_graph")) or self._as_list(llm_value.get("strengths")),
            "weaknesses": self._as_list(candidate.get("weak_points")),
            "contact_suggestion": str(llm_value.get("contact_suggestion") or "可以先围绕当前主题一起讨论。"),
            "collaboration_mode": str(llm_value.get("collaboration_mode") or "互问互答"),
        }
        if effective_graph_score is not None:
            result["graph_score"] = self._safe_float(effective_graph_score, 0)
        if effective_similarity_score is not None:
            result["similarity_score"] = self._safe_float(effective_similarity_score, 0)
        if candidate.get("rank") is not None:
            result["rank"] = self._safe_int(candidate.get("rank"), 0)
        return result

    async def _persist_recommendation(
        self,
        output: dict[str, Any],
        input_data: dict[str, Any],
        context: dict[str, Any],
        tool_results: dict[str, Any],
        plan_history: list[dict[str, Any]],
        reflection_history: list[dict[str, Any]],
    ) -> str:
        learner_id = self._learner_id({**input_data, **context})
        buddies = [dict(item) for item in output.get("buddies", []) if isinstance(item, dict)]
        if not learner_id or not buddies:
            return ""
        from app.database import AsyncSessionLocal
        from app.models.recommendation import BuddyRecommendation

        recommendation_id = str(uuid.uuid4())
        try:
            async with AsyncSessionLocal() as session:
                session.add(
                    BuddyRecommendation(
                        id=recommendation_id,
                        session_id=str(context.get("conversation_id") or "").strip() or None,
                        learner_id=learner_id,
                        candidates={"buddies": tool_results["candidates"]},
                        rec_num=len(buddies),
                        train_labels={
                            "planning": output.get("planning", {}),
                            "reflection": output.get("reflection", {}),
                            "tool_trace": output.get("tool_trace", []),
                            "execution_context": tool_results.get("execution_context", {}),
                            "plan_history": plan_history,
                            "reflection_history": reflection_history,
                        },
                        model_version=str(self.llm_config.get("model") or self.version),
                        rec_strategy=str(output.get("planning", {}).get("recall_strategy") or ""),
                        rec_partners={"buddies": buddies},
                        rec_ranks={
                            "buddies": [
                                {
                                    "rank": item.get("rank", index),
                                    "learner_id": item.get("user_id", ""),
                                    "graph_score": item.get("graph_score"),
                                    "similarity_score": item.get("similarity_score"),
                                    "complement_score": item.get("complement_score", 0),
                                }
                                for index, item in enumerate(buddies, start=1)
                            ]
                        },
                    )
                )
                await session.commit()
                return recommendation_id
        except Exception as exc:
            logger.warning("[study_buddy] persist recommendation failed: %s", exc)
            return ""

    def _fallback_summary(
        self,
        plan: dict[str, Any],
        tool_results: dict[str, Any],
        reflection: dict[str, Any],
    ) -> dict[str, Any]:
        buddies = tool_results["ranked_buddies"]
        text = (
            f"我更推荐你先和 {buddies[0].get('nickname', '这位同学')} 一起学习。"
            if buddies
            else "当前还没有找到合适的学伴，可以稍后再试。"
        )
        return {
            "recommendation_text": text,
            "buddies": buddies,
            "planning": self._planning_from_plan(plan),
            "matching_plan": {},
            "group_suggestion": {},
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
        planning = self._planning_from_plan(plan)
        recommendation_text = (
            "已完成学伴检索与排序。"
            if plan["need_tool"]
            else plan["final_answer"] or _BOUNDARY_MESSAGE
        )
        return self._ensure_output_shape(
            {
                "recommendation_text": recommendation_text,
                "planning": planning,
                "matching_plan": planning,
                "group_suggestion": {},
                "buddies": tool_results["ranked_buddies"],
                "rationale": plan["thought"],
                "sequence": [],
                "reflection": {},
                "tool_trace": tool_results["tool_trace"],
                "execution_context": tool_results["execution_context"],
                "plan_history": [plan],
                "reflection_history": [],
            },
            tool_results,
            plan,
            {},
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
                "matching_plan": {},
                "group_suggestion": {},
                "buddies": [],
                "rationale": "recommendation_only_boundary",
                "sequence": [],
                "reflection": {"passed": True, "coverage_score": 1, "compatibility_score": 1, "diversity_score": 1},
                "tool_trace": [],
                "plan_history": plan_history,
                "reflection_history": reflection_history,
            },
            self._empty_tool_results(),
            plan,
            {},
        )

    def _ensure_output_shape(
        self,
        output: dict[str, Any],
        tool_results: dict[str, Any],
        plan: dict[str, Any],
        reflection: dict[str, Any],
    ) -> dict[str, Any]:
        canonical = {
            str(item.get("user_id")): item
            for item in tool_results.get("ranked_buddies", [])
            if isinstance(item, dict) and item.get("user_id")
        }
        llm_buddies = {
            str(item.get("user_id")): item
            for item in self._as_list(output.get("buddies"))
            if isinstance(item, dict) and item.get("user_id")
        }
        buddies = [self._decorate_buddy(candidate, llm_buddies.get(candidate_id)) for candidate_id, candidate in canonical.items()]
        planning = output.get("planning") if isinstance(output.get("planning"), dict) else self._planning_from_plan(plan)
        reflection_output = output.get("reflection") if isinstance(output.get("reflection"), dict) else self._reflection_for_output(reflection)
        text_value = str(
            output.get("recommendation_text")
            or output.get("response_text")
            or output.get("content")
            or _BOUNDARY_MESSAGE
        )
        trace = [item for item in output.get("tool_trace", []) if isinstance(item, dict)]
        if not trace:
            trace = tool_results.get("tool_trace", [])
        execution_context = (
            output.get("execution_context")
            if isinstance(output.get("execution_context"), dict)
            else tool_results.get("execution_context", {})
        )
        buddy_list = {
            "buddies": buddies,
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
            "buddy_list": buddy_list,
            "planning": planning,
            "matching_plan": output.get("matching_plan") if isinstance(output.get("matching_plan"), dict) else planning,
            "buddies": buddies,
            "group_suggestion": output.get("group_suggestion") if isinstance(output.get("group_suggestion"), dict) else {},
            "rationale": buddy_list["rationale"],
            "sequence": buddy_list["sequence"],
            "reflection": reflection_output,
            "tool_trace": trace,
            "execution_context": execution_context,
            "plan_history": [item for item in output.get("plan_history", []) if isinstance(item, dict)],
            "reflection_history": [item for item in output.get("reflection_history", []) if isinstance(item, dict)],
        }

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
            "compatibility_score": reflection.get("compatibility_score", 0),
            "diversity_score": reflection.get("diversity_score", 0),
            "improvement_suggestion": reflection.get("suggestion", ""),
            "passed": reflection.get("passed", False),
            "forced_pass": reflection.get("forced_pass", False),
        }

    @staticmethod
    def _empty_tool_results() -> dict[str, Any]:
        return {"candidates": [], "ranked_buddies": [], "tool_trace": [], "execution_context": {}}

    @staticmethod
    def _prepare_plan_input(input_data: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        prepared = dict(input_data)
        if not prepared.get("user_id") and context.get("user_id"):
            prepared["user_id"] = str(context["user_id"])
        prepared.setdefault("recent_messages", [])
        prepared.setdefault("current_message", prepared.get("message", ""))
        return prepared

    @staticmethod
    def _row_learner_id(row: dict[str, Any]) -> str:
        return str(row.get("user_id") or row.get("learner_id") or row.get("id") or "")

    @staticmethod
    def _unique_ids(values: Any) -> list[str]:
        return list(dict.fromkeys(value for value in values if value))

    @staticmethod
    def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value.isoformat() if isinstance(value, datetime | date) else value
            for key, value in row.items()
        }

    @staticmethod
    def _dedupe_buddies(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_id = {str(item.get("user_id") or item.get("learner_id") or item.get("id") or ""): item for item in items if isinstance(item, dict)}
        return [item for learner_id, item in by_id.items() if learner_id]

    @staticmethod
    def _strong_knowledge(knowledge_graph: Any) -> list[str]:
        if not isinstance(knowledge_graph, dict):
            return []
        return [str(key) for key, value in knowledge_graph.items() if isinstance(value, int | float) and value >= 0.7][:5]

    @staticmethod
    def _learner_id(input_data: dict[str, Any]) -> str:
        return str(input_data.get("user_id") or input_data.get("learner_id") or "").strip()

    @staticmethod
    def _force_pass_reflection(reflection: dict[str, Any]) -> dict[str, Any]:
        return {**reflection, "passed": True, "forced_pass": True}

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
    def _merge_usage(total: dict[str, Any], usage: dict[str, Any]) -> None:
        for key, value in usage.items():
            total[key] = total.get(key, 0) + value if isinstance(value, int | float) else value
