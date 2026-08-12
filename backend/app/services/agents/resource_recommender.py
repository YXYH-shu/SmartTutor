"""Resource Recommender Agent - plan/tool/reflection/summary skeleton."""

from __future__ import annotations

import logging
import json
import re
import time
import uuid
from datetime import date, datetime
from typing import Any

import numpy as np
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from jinja2 import BaseLoader, Environment, StrictUndefined

from app.services.agents.base_agent import BaseAgent
from app.services.response_context import (
    build_response_diagnosis_context,
    build_response_profile_context,
)

logger = logging.getLogger(__name__)
_jinja_env = Environment(loader=BaseLoader(), undefined=StrictUndefined)

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
    """Lightweight orchestration shell for future recommendation logic."""

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
        t0 = time.perf_counter()

        logger.info("[resource_recommender] start trace=%s", trace_id)
        self._trace("[%s] NODE_ENTER resource_recommender", trace_id)

        enriched = await self.enrich_input(dict(input_data), context)
        usage: dict[str, Any] = {}
        plan_history: list[dict[str, Any]] = []
        reflection_history: list[dict[str, Any]] = []
        tool_results = self._empty_tool_results()
        reflection_result: dict[str, Any] = {}
        max_reflections = max(1, self._safe_int(self.config.get("max_reflection_attempts"), 2))

        while True:
            plan_payload, plan_usage = await self._generate_plan(enriched, reflection_result)
            self._merge_usage(usage, plan_usage)

            plan = self._parse_plan(plan_payload)
            plan_history.append(plan)
            self._trace("[%s] PLAN need_tool=%s", trace_id, plan.get("need_tool"))

            if not plan.get("need_tool", False):
                output, summary_usage = await self._summary(
                    plan,
                    tool_results,
                    enriched,
                    reflection_result,
                    plan_history=plan_history,
                    reflection_history=reflection_history,
                )
                self._merge_usage(usage, summary_usage)
                break

            tool_results = await self._execute_tools(plan, enriched)
            reflection_result, reflection_usage = await self._reflection(
                plan=plan,
                tool_results=tool_results,
                input_data=enriched,
            )
            self._merge_usage(usage, reflection_usage)
            reflection_history.append(reflection_result)
            self._trace(
                "[%s] REFLECTION attempt=%s passed=%s",
                trace_id,
                len(reflection_history),
                reflection_result.get("passed"),
            )

            if reflection_result.get("passed"):
                output, summary_usage = await self._summary(
                    plan,
                    tool_results,
                    enriched,
                    reflection_result,
                    plan_history=plan_history,
                    reflection_history=reflection_history,
                )
                self._merge_usage(usage, summary_usage)
                break

            if len(reflection_history) >= max_reflections:
                reflection_result = self._force_pass_reflection(reflection_result)
                reflection_history[-1] = reflection_result
                output, summary_usage = await self._summary(
                    plan,
                    tool_results,
                    enriched,
                    reflection_result,
                    plan_history=plan_history,
                    reflection_history=reflection_history,
                )
                self._merge_usage(usage, summary_usage)
                break

        recommendation_id = await self._persist_recommendation(
            output=output,
            input_data=enriched,
            context=context,
            tool_results=tool_results,
            plan_history=plan_history,
            reflection_history=reflection_history,
        )
        if recommendation_id:
            output["recommendation_id"] = recommendation_id
            if isinstance(output.get("resource_list"), dict):
                output["resource_list"]["recommendation_id"] = recommendation_id

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        await self._log_execution(
            conversation_id=context.get("conversation_id", ""),
            input_payload={
                "input": enriched,
                "plan_history": plan_history,
                "reflection_history": reflection_history,
                "tool_results": tool_results,
            },
            output_payload=output,
            execution_time_ms=elapsed_ms,
            turn_id=context.get("turn_id"),
        )
        await self.post_process(output, context)

        logger.info("[resource_recommender] done trace=%s latency_ms=%s", trace_id, elapsed_ms)
        self._trace("[%s] NODE_EXIT resource_recommender latency_ms=%s", trace_id, elapsed_ms)

        return {
            "agent": self.name,
            "output": output,
            "usage": usage,
            "latency_ms": elapsed_ms,
        }

    async def _generate_plan(
        self,
        input_data: dict[str, Any],
        reflection_result: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        prompt_data = dict(input_data)
        prompt_data["reflection_result"] = reflection_result or {}
        return await self._call_llm_json("plan", prompt_data)

    async def _reflection(
        self,
        plan: dict[str, Any],
        tool_results: dict[str, Any],
        input_data: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        prompt_data = dict(input_data)
        prompt_data.update(
            {
                "plan": plan,
                "tool_results": tool_results,
            }
        )
        payload, usage = await self._call_llm_json("reflection", prompt_data)
        reflection = self._parse_reflection(payload)
        return self._apply_reflection_checks(reflection, plan, tool_results), usage

    async def _summary(
        self,
        plan: dict[str, Any],
        tool_results: dict[str, Any],
        input_data: dict[str, Any],
        reflection_result: dict[str, Any],
        *,
        plan_history: list[dict[str, Any]] | None = None,
        reflection_history: list[dict[str, Any]] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        prompt_data = dict(input_data)
        prompt_data.update(
            {
                "plan": plan,
                "tool_results": tool_results,
                "reflection_result": reflection_result,
            }
        )
        payload, usage = await self._call_llm_json("summary", prompt_data)
        if not payload:
            payload = self._fallback_summary(plan, tool_results, reflection_result)

        if not payload.get("planning"):
            payload["planning"] = self._planning_from_plan(plan)
        if not payload.get("resources"):
            payload["resources"] = tool_results.get("ranked_resources", [])
        if not payload.get("reflection"):
            payload["reflection"] = self._reflection_for_output(reflection_result)
        if not payload.get("tool_trace"):
            payload["tool_trace"] = tool_results.get("tool_trace", [])
        if not payload.get("query_results"):
            payload["query_results"] = tool_results.get("query_results", [])
        if not payload.get("candidate_store"):
            payload["candidate_store"] = tool_results.get("candidate_store", {})
        if not payload.get("unmatched_candidate_items"):
            candidate_store = tool_results.get("candidate_store", {})
            payload["unmatched_candidate_items"] = candidate_store.get("unmatched_items", [])
        # Carry plan/reflection trace so the front-end AgentDetailDrawer can
        # surface the plan → tool → reflection loop without parsing execution logs.
        payload["plan_history"] = list(plan_history or [])
        payload["reflection_history"] = list(reflection_history or [])
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
        resources = [
            dict(item)
            for item in output.get("resources", [])
            if isinstance(item, dict)
        ]
        if not resources:
            logger.info("[resource_recommender] skip recommendation persistence: no resources")
            return ""

        learner_id = str(context.get("user_id") or input_data.get("user_id") or "").strip()
        if not learner_id:
            logger.info("[resource_recommender] skip recommendation persistence: no user_id")
            return ""

        session_id = str(
            context.get("conversation_id") or input_data.get("conversation_id") or ""
        ).strip() or None
        recommendation_id = str(uuid.uuid4())

        rec_ranks = [
            {
                "rank": index,
                "resource_id": item.get("id") or item.get("resource_id") or "",
                "title": item.get("title") or item.get("name") or "",
                "recommend_reason": item.get("recommend_reason") or "",
            }
            for index, item in enumerate(resources, start=1)
        ]
        labels = {
            "planning": output.get("planning", {}),
            "reflection": output.get("reflection", {}),
            "tool_trace": output.get("tool_trace", []),
            "candidate_store": output.get("candidate_store", {}),
            "plan_history": plan_history,
            "reflection_history": reflection_history,
            "current_message": input_data.get("current_message", ""),
            "target_knowledge": input_data.get("target_knowledge", []),
        }

        try:
            from app.database import AsyncSessionLocal
            from app.models.recommendation import ResourceRecommendation

            async with AsyncSessionLocal() as session:
                session.add(
                    ResourceRecommendation(
                        id=recommendation_id,
                        session_id=session_id,
                        learner_id=learner_id,
                        candidates={
                            "resources": [
                                dict(item)
                                for item in tool_results.get("candidates", [])
                                if isinstance(item, dict)
                            ],
                        },
                        rec_num=len(resources),
                        labels=labels,
                        kg_version=(
                            str(input_data.get("kg_version"))
                            if input_data.get("kg_version") is not None
                            else None
                        ),
                        model_version=str(self.llm_config.get("model") or self.version),
                        rec_resources={"resources": resources},
                        rec_ranks={"resources": rec_ranks},
                        feedback_score=None,
                    )
                )
                await session.commit()
        except Exception as exc:
            logger.warning("[resource_recommender] persist recommendation failed: %s", exc)
            return ""

        logger.info("[resource_recommender] persisted recommendation id=%s", recommendation_id)
        return recommendation_id

    async def _call_llm_json(self, stage: str, data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        llm_cfg = self.llm_config
        result = await self.llm.chat_completion(
            prompt=self._render_stage_prompt(stage, data),
            system_prompt=None,
            model=llm_cfg.get("model"),
            temperature=llm_cfg.get("temperature", 0.2),
            max_tokens=llm_cfg.get("max_tokens"),
            response_format="json",
            thinking=llm_cfg.get("thinking", False),
        )

        content = result.get("content", {})
        if isinstance(content, dict):
            return content, result.get("usage", {})

        logger.warning("[resource_recommender] %s response is not a JSON object", stage)
        return {}, result.get("usage", {})

    def _render_stage_prompt(self, stage: str, data: dict[str, Any]) -> str:
        key = f"{stage}_prompt_template"
        template = self.config.get(key) or (self.system_prompt_template if stage == "plan" else "")
        if not template:
            raise ValueError(f"Missing prompt template for resource_recommender.{stage}")
        return _jinja_env.from_string(template).render(**data)

    async def _execute_tools(
        self,
        plan: dict[str, Any],
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Tool orchestration skeleton. Fill concrete tools later."""
        candidates: list[dict[str, Any]] = []
        query_results: list[dict[str, Any]] = []
        ranked_resources: list[dict[str, Any]] = []
        tool_trace: list[dict[str, Any]] = []
        candidate_scope_active = False
        candidate_store = self._empty_candidate_store_result()

        for call in plan.get("tool_calls", []):
            tool_name = str(call.get("tool_name", ""))
            tool_key = self._normalize_tool_name(tool_name)
            tool_input = call.get("input", call.get("arguments", {}))
            if not isinstance(tool_input, dict):
                tool_input = {}
            trace_extra: dict[str, Any] = {}

            if tool_key == "CandidateStoreTool":
                result, store_meta = await self._candidate_store_tool_result(tool_input, input_data)
                candidates = self._dedupe_resources([*candidates, *result])
                candidate_scope_active = True
                candidate_store = self._merge_candidate_store_result(candidate_store, store_meta)
                trace_extra = {
                    "matched_items": store_meta.get("matched_items", []),
                    "unmatched_items": store_meta.get("unmatched_items", []),
                    "matched_resource_ids": store_meta.get("matched_resource_ids", []),
                }
            elif tool_key == "QueryTool":
                result = await self._query_tool(tool_input, input_data)
                query_results.extend(result)
            elif tool_key == "SqlRetrievalTool":
                result = await self._sql_retrieval_tool(tool_input, input_data)
                if candidate_scope_active:
                    candidates = self._intersect_candidates_by_resource_ids(candidates, result)
                else:
                    candidates.extend(result)
            elif tool_key == "ItemCfRetrievalTool":
                result = await self._item_cf_retrieval_tool(tool_input, candidates, input_data)
                candidates = result
            elif tool_key == "RankingTool":
                result = await self._ranking_tool(tool_input, candidates, input_data)
                ranked_resources = result
            else:
                result = []

            status = "executed" if tool_key in {
                "QueryTool",
                "CandidateStoreTool",
                "SqlRetrievalTool",
                "ItemCfRetrievalTool",
                "RankingTool",
            } else "placeholder"
            trace_entry = {
                "tool": tool_key or tool_name or "unknown_tool",
                "status": status,
                "input": tool_input,
                "count": self._count_tool_result(result),
            }
            trace_entry.update(trace_extra)
            tool_trace.append(trace_entry)

        if not ranked_resources:
            ranked_resources = candidates

        return {
            "candidates": candidates,
            "query_results": query_results,
            "ranked_resources": ranked_resources,
            "tool_trace": tool_trace,
            "candidate_store": candidate_store,
        }

    async def _candidate_store_tool(self, tool_input: dict[str, Any], input_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Resolve user-provided candidate resource names into resource candidates."""
        candidates, _ = await self._candidate_store_tool_result(tool_input, input_data)
        return candidates

    async def _candidate_store_tool_result(
        self,
        tool_input: dict[str, Any],
        input_data: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        source_items = self._candidate_store_source_items(tool_input)
        meta = self._empty_candidate_store_result()
        meta["requested_items"] = source_items
        if not source_items:
            logger.warning("[resource_recommender] CandidateStoreTool missing items")
            return [], meta

        from app.database import AsyncSessionLocal
        from app.models.learning_resource import LearningResource

        rows: list[dict[str, Any]] = []
        source_by_resource_id: dict[str, list[str]] = {}
        async with AsyncSessionLocal() as session:
            for source_item in source_items:
                result = await session.execute(
                    select(*self._learning_resource_columns())
                    .where(LearningResource.name.contains(source_item, autoescape=True))
                    .order_by(LearningResource.name)
                )
                matched_rows = [self._serialize_row(dict(row)) for row in result.mappings().all()]
                if not matched_rows:
                    self._append_unique(meta["unmatched_items"], source_item)
                    continue

                self._append_unique(meta["matched_items"], source_item)
                for row in matched_rows:
                    resource_id = str(row.get("id") or "")
                    if resource_id:
                        source_by_resource_id.setdefault(resource_id, [])
                        self._append_unique(source_by_resource_id[resource_id], source_item)
                    rows.append(row)

        candidates = await self._rows_to_resource_candidates(rows)
        for candidate in candidates:
            resource_id = str(candidate.get("id") or "")
            candidate["recommend_reason"] = "由 CandidateStoreTool 根据用户指定候选资源名称匹配召回。"
            candidate["source_items"] = source_by_resource_id.get(resource_id, [])
            if resource_id:
                self._append_unique(meta["matched_resource_ids"], resource_id)

        meta["matches"] = [
            {
                "resource_id": candidate.get("id"),
                "title": candidate.get("title"),
                "source_items": candidate.get("source_items", []),
            }
            for candidate in candidates
        ]
        return candidates, meta

    def _candidate_store_source_items(self, tool_input: dict[str, Any]) -> list[str]:
        raw_items = (
            tool_input.get("items")
            or tool_input.get("item")
            or tool_input.get("resources")
            or tool_input.get("resource")
            or tool_input.get("candidates")
        )
        items: list[str] = []
        for item in self._as_list(raw_items):
            if item is None:
                continue
            for part in re.split(r"[,，、;；\n\r]+", str(item)):
                value = part.strip()
                if value:
                    self._append_unique(items, value)
        return items

    def _empty_candidate_store_result(self) -> dict[str, Any]:
        return {
            "requested_items": [],
            "matched_items": [],
            "unmatched_items": [],
            "matched_resource_ids": [],
            "matches": [],
        }

    def _merge_candidate_store_result(
        self,
        base: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        merged = {
            "requested_items": list(self._as_list(base.get("requested_items"))),
            "matched_items": list(self._as_list(base.get("matched_items"))),
            "unmatched_items": list(self._as_list(base.get("unmatched_items"))),
            "matched_resource_ids": list(self._as_list(base.get("matched_resource_ids"))),
            "matches": [
                item
                for item in self._as_list(base.get("matches"))
                if isinstance(item, dict)
            ],
        }
        for key in ("requested_items", "matched_items", "unmatched_items", "matched_resource_ids"):
            for item in self._as_list(incoming.get(key)):
                self._append_unique(merged[key], str(item))

        seen_matches = {
            str(item.get("resource_id") or "")
            for item in merged["matches"]
            if isinstance(item, dict)
        }
        for item in self._as_list(incoming.get("matches")):
            if not isinstance(item, dict):
                continue
            resource_id = str(item.get("resource_id") or "")
            if resource_id and resource_id in seen_matches:
                continue
            merged["matches"].append(item)
            if resource_id:
                seen_matches.add(resource_id)
        return merged

    def _intersect_candidates_by_resource_ids(
        self,
        candidates: list[dict[str, Any]],
        filters: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        filter_ids = set(self._extract_resource_ids(filters))
        if not filter_ids:
            return []
        return [
            candidate
            for candidate in candidates
            if self._row_resource_id(candidate) in filter_ids
        ]

    async def _query_tool(self, tool_input: dict[str, Any], input_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Execute a read-only information query against resource tables."""
        sql = self._extract_sql(tool_input)
        if not sql:
            logger.warning("[resource_recommender] QueryTool missing sql")
            return []

        try:
            return await self._run_select_sql(sql)
        except (ValueError, SQLAlchemyError) as exc:
            logger.warning("[resource_recommender] QueryTool failed: %s", exc)
            return []

    async def _sql_retrieval_tool(self, tool_input: dict[str, Any], input_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Recall candidate learning resources with a read-only SQL query."""
        sql = self._extract_sql(tool_input)
        if not sql:
            logger.warning("[resource_recommender] SqlRetrievalTool missing sql")
            return []

        try:
            rows = await self._run_select_sql(sql)
            return await self._rows_to_resource_candidates(rows)
        except (ValueError, SQLAlchemyError) as exc:
            logger.warning("[resource_recommender] SqlRetrievalTool failed: %s", exc)
            return []

    async def _item_cf_retrieval_tool(
        self,
        tool_input: dict[str, Any],
        candidates: list[dict[str, Any]],
        input_data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Retrieve resources similar to anchor items using resource embeddings."""
        source_items = self._item_cf_source_items(tool_input)
        if not source_items:
            logger.warning("[resource_recommender] ItemCfRetrievalTool missing items")
            return []

        anchors = await self._resolve_item_cf_anchor_resources(source_items)
        anchor_vectors = [
            (row, vector)
            for row in anchors
            if (vector := self._parse_embed_vector(row.get("embed")))
        ]
        if not anchor_vectors:
            logger.warning("[resource_recommender] ItemCfRetrievalTool no anchor embeds found")
            return []

        scoped_ids = self._extract_resource_ids(candidates)
        if candidates and not scoped_ids:
            logger.warning("[resource_recommender] ItemCfRetrievalTool candidates missing ids")
            return []

        candidate_rows = await self._fetch_item_cf_candidate_resources(
            scoped_ids if candidates else None,
        )
        anchor_ids = {str(row.get("id")) for row, _ in anchor_vectors}
        source_labels = [
            str(row.get("name") or row.get("id"))
            for row, _ in anchor_vectors
            if row.get("name") or row.get("id")
        ] or source_items

        anchor_groups: dict[int, list[tuple[dict[str, Any], list[float]]]] = {}
        for row, vector in anchor_vectors:
            anchor_groups.setdefault(len(vector), []).append((row, vector))

        candidate_groups: dict[int, list[tuple[dict[str, Any], list[float]]]] = {}
        skipped_dimension_count = 0
        skipped_dimension_examples: list[str] = []
        threshold = self._safe_float(tool_input.get("threshold"), 0.2)
        for row in candidate_rows:
            resource_id = str(row.get("id") or "")
            if not resource_id or resource_id in anchor_ids:
                continue
            vector = self._parse_embed_vector(row.get("embed"))
            if not vector:
                continue
            vector_dim = len(vector)
            if vector_dim not in anchor_groups:
                skipped_dimension_count += 1
                if len(skipped_dimension_examples) < 5:
                    skipped_dimension_examples.append(resource_id)
                continue
            candidate_groups.setdefault(vector_dim, []).append((row, vector))

        if skipped_dimension_count:
            logger.warning(
                "[resource_recommender] ItemCfRetrievalTool skipped %s candidates with unmatched embedding dimensions: %s",
                skipped_dimension_count,
                skipped_dimension_examples,
            )

        scored: list[dict[str, Any]] = []
        for dim, grouped_candidates in candidate_groups.items():
            grouped_anchors = anchor_groups.get(dim, [])
            if not grouped_anchors:
                continue

            anchor_matrix = self._normalized_embedding_matrix(
                [vector for _, vector in grouped_anchors]
            )
            candidate_matrix = self._normalized_embedding_matrix(
                [vector for _, vector in grouped_candidates]
            )
            if anchor_matrix.size == 0 or candidate_matrix.size == 0:
                continue

            similarity_scores = candidate_matrix @ anchor_matrix.T
            best_anchor_indexes = np.argmax(similarity_scores, axis=1)
            best_scores = similarity_scores[
                np.arange(similarity_scores.shape[0]),
                best_anchor_indexes,
            ]

            for candidate_index, (row, _) in enumerate(grouped_candidates):
                best_score = float(best_scores[candidate_index])
                if best_score < threshold:
                    continue

                best_anchor_row = grouped_anchors[int(best_anchor_indexes[candidate_index])][0]
                best_anchor = str(best_anchor_row.get("name") or best_anchor_row.get("id") or "")

                candidate = self._resource_row_to_candidate(row)
                candidate["recommend_reason"] = "由 ItemCfRetrievalTool 根据资源 embedding 相似度召回。"
                candidate["similarity_score"] = best_score
                candidate["similarity_reason"] = (
                    f"Embedding cosine similarity with {best_anchor or 'source item'} is {best_score:.4f}."
                )
                candidate["source_items"] = source_labels
                scored.append(candidate)

        scored.sort(key=lambda item: self._safe_float(item.get("similarity_score"), 0), reverse=True)
        num = self._safe_int(tool_input.get("num"), 20)
        return scored[:num] if num > 0 else scored

    def _item_cf_source_items(self, tool_input: dict[str, Any]) -> list[str]:
        raw_items = (
            tool_input.get("items")
            or tool_input.get("item")
            or tool_input.get("resources")
            or tool_input.get("resource")
        )
        return [
            str(item).strip()
            for item in self._as_list(raw_items)
            if str(item).strip()
        ]

    async def _resolve_item_cf_anchor_resources(self, items: list[str]) -> list[dict[str, Any]]:
        from app.database import AsyncSessionLocal
        from app.models.learning_resource import LearningResource

        columns = self._learning_resource_columns(include_embed=True)
        anchors: list[dict[str, Any]] = []
        seen: set[str] = set()

        async with AsyncSessionLocal() as session:
            exact_result = await session.execute(
                select(*columns).where(LearningResource.id.in_(items))
            )
            for row in exact_result.mappings().all():
                item = self._serialize_row(dict(row))
                resource_id = str(item.get("id") or "")
                if resource_id and resource_id not in seen:
                    anchors.append(item)
                    seen.add(resource_id)

            for raw_item in items:
                if raw_item in seen:
                    continue
                name_result = await session.execute(
                    select(*columns)
                    .where(LearningResource.name.like(f"%{raw_item}%"))
                    .order_by(LearningResource.name)
                    .limit(1)
                )
                row = name_result.mappings().first()
                if not row:
                    continue
                item = self._serialize_row(dict(row))
                resource_id = str(item.get("id") or "")
                if resource_id and resource_id not in seen:
                    anchors.append(item)
                    seen.add(resource_id)

        return anchors

    async def _fetch_item_cf_candidate_resources(
        self,
        resource_ids: list[str] | None,
    ) -> list[dict[str, Any]]:
        from app.database import AsyncSessionLocal
        from app.models.learning_resource import LearningResource

        if resource_ids is not None and not resource_ids:
            return []

        query = select(*self._learning_resource_columns(include_embed=True)).where(
            LearningResource.embed.is_not(None),
            LearningResource.embed != "",
        )
        if resource_ids is not None:
            query = query.where(LearningResource.id.in_(resource_ids))

        async with AsyncSessionLocal() as session:
            result = await session.execute(query)
            return [
                self._serialize_row(dict(row))
                for row in result.mappings().all()
            ]

    def _learning_resource_columns(self, include_embed: bool = False) -> list[Any]:
        from app.models.learning_resource import LearningResource

        columns = [
            LearningResource.id,
            LearningResource.name,
            LearningResource.content,
            LearningResource.type,
            LearningResource.url,
            LearningResource.difficult,
            LearningResource.time_need,
        ]
        if include_embed:
            columns.append(LearningResource.embed)
        return columns

    def _parse_embed_vector(self, value: Any) -> list[float]:
        if value in (None, ""):
            return []
        raw = value
        if isinstance(value, str):
            try:
                raw = json.loads(value)
            except json.JSONDecodeError:
                return []
        if not isinstance(raw, list):
            return []

        vector: list[float] = []
        for item in raw:
            try:
                vector.append(float(item))
            except (TypeError, ValueError):
                return []
        return vector if any(component != 0 for component in vector) else []

    def _normalized_embedding_matrix(self, vectors: list[list[float]]) -> np.ndarray:
        if not vectors:
            return np.empty((0, 0), dtype=np.float32)
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.ndim != 2:
            return np.empty((0, 0), dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        if np.any(norms == 0):
            return np.empty((0, 0), dtype=np.float32)
        return matrix / norms

    def _cosine_similarity(self, left: list[float], right: list[float]) -> float:
        if not left or not right:
            return 0.0
        if len(left) != len(right):
            logger.warning(
                "[resource_recommender] skip cosine similarity for dimension mismatch: %s vs %s",
                len(left),
                len(right),
            )
            return 0.0
        left_array = np.asarray(left, dtype=np.float32)
        right_array = np.asarray(right, dtype=np.float32)
        left_norm = float(np.linalg.norm(left_array))
        right_norm = float(np.linalg.norm(right_array))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return float(np.dot(left_array, right_array) / (left_norm * right_norm))

    async def _ranking_tool(
        self,
        tool_input: dict[str, Any],
        candidates: list[dict[str, Any]],
        input_data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Prepare CTR ranking features, score if a model is available, then truncate."""
        ranked = self._dedupe_resources(candidates)
        schema = str(tool_input.get("schema") or "personality")
        num = self._safe_int(tool_input.get("num"), 0)

        ctr_scores: list[float] = []
        if schema == "personality":
            ctr_instances = await self._prepare_ctr_ranking_instances(
                candidates=ranked,
                input_data=input_data,
                tool_input=tool_input,
            )
            ctr_scores = await self._predict_ctr_scores(ctr_instances, tool_input, input_data)

        if len(ctr_scores) == len(ranked):
            for item, score in zip(ranked, ctr_scores, strict=False):
                item["ctr_score"] = self._safe_float(score, 0)
            ranked.sort(key=lambda item: self._safe_float(item.get("ctr_score"), 0), reverse=True)
        else:
            ranked = self._fallback_rank_resources(ranked, schema, input_data)

        if num > 0:
            ranked = ranked[:num]
        for index, item in enumerate(ranked, start=1):
            item["rank"] = index
        return ranked

    async def _prepare_ctr_ranking_instances(
        self,
        candidates: list[dict[str, Any]],
        input_data: dict[str, Any],
        tool_input: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Build one CTR model input row per candidate resource."""
        tool_input = tool_input or {}
        learner_id = str(input_data.get("user_id") or input_data.get("learner_id") or "").strip()
        sequence_limit = self._safe_int(tool_input.get("sequence_limit"), 50)
        sequence_features = await self._fetch_interaction_sequence_features(
            learner_id=learner_id,
            limit=sequence_limit,
        )
        user_features = self._build_ctr_user_features(input_data, sequence_features)
        context_features = self._build_ctr_context_features(input_data, tool_input)

        return [
            {
                "user_features": user_features,
                "item_features": self._build_ctr_item_features(candidate),
                "sequence_features": sequence_features,
                "context_features": context_features,
            }
            for candidate in candidates
        ]

    async def _predict_ctr_scores(
        self,
        instances: list[dict[str, Any]],
        tool_input: dict[str, Any],
        input_data: dict[str, Any],
    ) -> list[float]:
        """CTR model hook. Return one score per instance when a predictor is wired in."""
        if not instances:
            return []
        try:
            from app.services.resource_ranking_predictor import get_resource_ranking_predictor

            return get_resource_ranking_predictor().predict(instances)
        except Exception as exc:
            logger.warning("[resource_recommender] CTR ranking failed: %s", exc)
            return []

    def _fallback_rank_resources(
        self,
        resources: list[dict[str, Any]],
        schema: str,
        input_data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        ranked = list(resources)
        if schema == "time_need":
            ranked.sort(key=lambda item: self._resource_time_needed(item))
        elif schema == "difficulty":
            target = self._difficulty_target(input_data)
            ranked.sort(key=lambda item: abs(self._resource_difficulty_score(item) - target))
        elif schema == "similarity":
            ranked.sort(
                key=lambda item: self._safe_float(item.get("similarity_score") or item.get("score"), 0),
                reverse=True,
            )
        return ranked

    def _build_ctr_user_features(
        self,
        input_data: dict[str, Any],
        sequence_features: dict[str, Any],
    ) -> dict[str, Any]:
        profile = input_data.get("user_profile") if isinstance(input_data.get("user_profile"), dict) else {}
        knowledge_graph = input_data.get("knowledge_graph") or profile.get("knowledge_graph") or {}
        weak_points = input_data.get("weak_points") or profile.get("weak_points") or []
        preferences = input_data.get("preferences") or profile.get("preferences") or {}
        current_level = input_data.get("current_level") or profile.get("current_level")
        learning_style = input_data.get("learning_style") or profile.get("learning_style")
        grade_level = input_data.get("grade_level") or profile.get("grade_level")
        interaction = sequence_features.get("interaction", {})

        mastery_values = [
            self._safe_float(value, 0)
            for value in (knowledge_graph.values() if isinstance(knowledge_graph, dict) else [])
            if isinstance(value, int | float)
        ]

        return {
            "user_id": self._category_id("user_id", input_data.get("user_id") or input_data.get("learner_id")),
            "current_level": self._category_id("current_level", current_level),
            "grade_level": self._category_id("grade_level", grade_level),
            "learning_style": self._category_id("learning_style", learning_style),
            "weak_points": self._category_list("knowledge", weak_points),
            "preference_keys": self._category_list(
                "preference_key",
                preferences.keys() if isinstance(preferences, dict) else [],
            ),
            "knowledge_mastery_avg": self._avg_or_none(mastery_values),
            "weak_point_count": float(len(self._as_list(weak_points))),
            "history_length": float(len(interaction.get("resource_id_seq", []))),
        }

    def _build_ctr_item_features(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "resource_id": self._category_id("resource_id", item.get("id") or item.get("resource_id")),
            "resource_type": self._category_id("resource_type", item.get("type")),
            "knowledge_tags": self._category_list(
                "knowledge",
                item.get("knowledge_tags") or item.get("tags") or item.get("knowledge_coverage"),
            ),
            "difficulty": self._resource_difficulty_score(item),
            "time_need": float(self._resource_time_needed(item)) if self._resource_time_needed(item) < 10**9 else None,
            "has_url": 1.0 if item.get("url") else 0.0,
            "full_score": self._optional_float(item.get("full_score")),
            "similarity_score": self._optional_float(item.get("similarity_score") or item.get("score")),
        }

    def _build_ctr_context_features(
        self,
        input_data: dict[str, Any],
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "stage": self._category_id("stage", input_data.get("stage")),
            "ranking_schema": self._category_id("ranking_schema", tool_input.get("schema") or "personality"),
            "target_knowledge": self._category_list("knowledge", input_data.get("target_knowledge")),
            "requested_num": float(self._safe_int(tool_input.get("num"), 0)),
        }

    async def _fetch_interaction_sequence_features(
        self,
        learner_id: str,
        limit: int,
    ) -> dict[str, Any]:
        if not learner_id:
            return self._empty_interaction_sequence_features()

        try:
            from app.database import AsyncSessionLocal
            from app.models.learner_interaction import LearnerResourceInteraction
            from app.models.learning_resource import LearningResource

            async with AsyncSessionLocal() as session:
                query = (
                    select(
                        LearnerResourceInteraction.resource_id,
                        LearnerResourceInteraction.learn_time,
                        LearnerResourceInteraction.learn_score,
                        LearnerResourceInteraction.emotion_category,
                        LearnerResourceInteraction.is_rec,
                        LearnerResourceInteraction.feedback_score,
                        LearnerResourceInteraction.result_type,
                        LearnerResourceInteraction.is_correct,
                        LearnerResourceInteraction.score,
                        LearnerResourceInteraction.created_at,
                        LearningResource.type.label("resource_type"),
                        LearningResource.difficult.label("resource_difficulty"),
                        LearningResource.time_need.label("resource_time_need"),
                    )
                    .outerjoin(
                        LearningResource,
                        LearnerResourceInteraction.resource_id == LearningResource.id,
                    )
                    .where(LearnerResourceInteraction.learner_id == learner_id)
                    .order_by(LearnerResourceInteraction.created_at.desc())
                    .limit(max(1, limit))
                )
                result = await session.execute(
                    query,
                )
                rows = [self._serialize_row(dict(row)) for row in result.mappings().all()]
        except SQLAlchemyError as exc:
            logger.warning("[resource_recommender] fetch interaction sequence failed: %s", exc)
            return self._empty_interaction_sequence_features()

        return self._rows_to_interaction_sequence_features(rows)

    def _rows_to_interaction_sequence_features(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        chronological = list(reversed(rows))
        interaction = {
            "resource_id_seq": [
                self._category_id("resource_id", row.get("resource_id"))
                for row in chronological
            ],
            "resource_type_seq": [
                self._category_id("resource_type", row.get("resource_type"))
                for row in chronological
            ],
            "result_type_seq": [
                self._category_id("result_type", row.get("result_type"))
                for row in chronological
            ],
            "emotion_category_seq": [
                self._category_id("emotion_category", row.get("emotion_category"))
                for row in chronological
            ],
            "is_rec_seq": [self._optional_bool_int(row.get("is_rec")) for row in chronological],
            "is_correct_seq": [self._optional_bool_int(row.get("is_correct")) for row in chronological],
            "learn_time_seq": [self._optional_float(row.get("learn_time")) for row in chronological],
            "learn_score_seq": [self._optional_float(row.get("learn_score")) for row in chronological],
            "feedback_score_seq": [self._optional_float(row.get("feedback_score")) for row in chronological],
            "score_seq": [self._optional_float(row.get("score")) for row in chronological],
            "resource_difficulty_seq": [
                self._optional_float(row.get("resource_difficulty"))
                for row in chronological
            ],
            "resource_time_need_seq": [
                self._optional_float(row.get("resource_time_need"))
                for row in chronological
            ],
            "created_at_seq": [row.get("created_at") for row in chronological],
        }
        self._assert_equal_sequence_lengths(interaction)
        return {"interaction": interaction}

    def _empty_interaction_sequence_features(self) -> dict[str, Any]:
        return {
            "interaction": {
                "resource_id_seq": [],
                "resource_type_seq": [],
                "result_type_seq": [],
                "emotion_category_seq": [],
                "is_rec_seq": [],
                "is_correct_seq": [],
                "learn_time_seq": [],
                "learn_score_seq": [],
                "feedback_score_seq": [],
                "score_seq": [],
                "resource_difficulty_seq": [],
                "resource_time_need_seq": [],
                "created_at_seq": [],
            }
        }

    def _assert_equal_sequence_lengths(self, sequence: dict[str, Any]) -> None:
        lengths = {
            key: len(value)
            for key, value in sequence.items()
            if isinstance(value, list)
        }
        if len(set(lengths.values())) > 1:
            raise ValueError(f"interaction sequence fields must have equal length: {lengths}")

    def _category_id(self, namespace: str, value: Any) -> Any:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        return str(value)

    def _category_list(self, namespace: str, value: Any) -> list[Any]:
        if isinstance(value, dict):
            values = value.keys()
        else:
            values = self._as_list(value)
        return [
            mapped
            for mapped in (self._category_id(namespace, item) for item in values)
            if mapped is not None
        ]

    def _optional_float(self, value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _optional_bool_int(self, value: Any) -> int | None:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes"}:
                return 1
            if lowered in {"false", "0", "no"}:
                return 0
            return None
        return int(bool(value))

    def _avg_or_none(self, values: list[float]) -> float | None:
        if not values:
            return None
        return sum(values) / len(values)

    def _parse_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Parse the planner JSON with minimal normalization."""
        tool_calls = payload.get("tool_calls", [])
        if not isinstance(tool_calls, list):
            tool_calls = []

        return {
            "need_tool": bool(payload.get("need_tool", False)),
            "question": str(payload.get("question") or ""),
            "thought": str(payload.get("thought") or ""),
            "final_answer": str(payload.get("final_answer") or ""),
            "target_knowledge": self._as_list(payload.get("target_knowledge")),
            "target_count": self._safe_int(payload.get("target_count"), 0),
            "recall_strategy": str(payload.get("recall_strategy") or ""),
            "ranking_criteria": self._as_list(payload.get("ranking_criteria")),
            "tool_calls": [
                {
                    "tool_name": self._normalize_tool_name(str(call.get("tool_name") or "")),
                    "input": call.get("input") if isinstance(call.get("input"), dict) else {},
                    "purpose": str(call.get("purpose") or ""),
                }
                for call in tool_calls
                if isinstance(call, dict)
            ],
        }

    def _parse_reflection(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "passed": payload.get("passed") is True,
            "issues": self._as_list(payload.get("issues")),
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
        """Add deterministic checks for common recommendation failures."""
        tool_names = {
            str(call.get("tool_name") or "")
            for call in plan.get("tool_calls", [])
            if isinstance(call, dict)
        }
        target_count = self._safe_int(plan.get("target_count"), 0)
        is_recommendation = target_count > 0 or any(
            name in tool_names
            for name in {"CandidateStoreTool", "SqlRetrievalTool", "ItemCfRetrievalTool", "RankingTool"}
        )
        if not is_recommendation:
            return reflection

        ranked_count = len(
            [item for item in tool_results.get("ranked_resources", []) if isinstance(item, dict)]
        )
        issues = [str(item) for item in self._as_list(reflection.get("issues")) if item]
        suggestions: list[str] = []

        if target_count > 0 and "RankingTool" not in tool_names:
            self._append_unique(issues, "推荐请求缺少 RankingTool，无法保证最终数量和顺序。")
            suggestions.append("下一轮 plan 需要在召回工具之后追加 RankingTool。")

        if target_count > 0 and ranked_count == 0:
            self._append_unique(issues, f"推荐结果为空，未满足目标数量 {target_count}。")
            suggestions.append("下一轮 plan 应扩大召回范围，避免过窄 SQL 条件。")
        elif target_count > 0 and ranked_count < target_count:
            self._append_unique(issues, f"推荐结果数量不足：目标 {target_count} 个，当前仅 {ranked_count} 个。")
            suggestions.append(
                "下一轮 plan 应放宽筛选条件，例如减少难度/类型限制，或先扩大召回再交给 RankingTool 截断。"
            )

        if issues:
            reflection["passed"] = False
            reflection["issues"] = issues
            merged_suggestion = "；".join(item for item in [reflection.get("suggestion"), *suggestions] if item)
            reflection["suggestion"] = merged_suggestion
            reflection["coverage_score"] = min(self._safe_float(reflection.get("coverage_score"), 0), 0.5)
            reflection["difficulty_match"] = min(self._safe_float(reflection.get("difficulty_match"), 0), 0.7)
        return reflection

    def _extract_sql(self, tool_input: dict[str, Any]) -> str:
        sql = tool_input.get("sql") or tool_input.get("query") or tool_input.get("statement") or ""
        return str(sql).strip()

    async def _run_select_sql(self, sql: str) -> list[dict[str, Any]]:
        safe_sql = self._validate_select_sql(sql)
        from app.database import AsyncSessionLocal, engine

        # 双重防御:在已有的白名单/黑名单校验之上,强制 session 只读,
        # 即使白名单被绕过,也无法执行任何 DDL/DML 写入。
        dialect_name = engine.dialect.name
        async with AsyncSessionLocal() as session:
            if dialect_name == "sqlite":
                await session.execute(text("PRAGMA query_only = ON"))
            elif dialect_name == "mysql":
                await session.execute(text("SET SESSION TRANSACTION READ ONLY"))
            try:
                result = await session.execute(text(safe_sql))
                return [self._serialize_row(dict(row)) for row in result.mappings().all()]
            finally:
                if dialect_name == "mysql":
                    await session.execute(text("SET SESSION TRANSACTION READ WRITE"))

    def _validate_select_sql(self, sql: str) -> str:
        normalized = sql.strip()
        if normalized.endswith(";"):
            normalized = normalized[:-1].strip()
        if not normalized:
            raise ValueError("empty sql")
        if ";" in normalized:
            raise ValueError("only one sql statement is allowed")
        if "--" in normalized or "/*" in normalized or "*/" in normalized:
            raise ValueError("sql comments are not allowed")

        compact = re.sub(r"\s+", " ", normalized).lower()
        if not compact.startswith("select "):
            raise ValueError("only SELECT statements are allowed")

        blocked = [word for word in _BLOCKED_SQL_KEYWORDS if re.search(rf"\b{word}\b", compact)]
        if blocked:
            raise ValueError(f"blocked sql keyword: {blocked[0]}")

        tables = self._extract_sql_tables(compact)
        if not tables:
            raise ValueError("sql must read from an allowed resource table")
        unexpected = sorted(tables - _ALLOWED_SQL_TABLES)
        if unexpected:
            raise ValueError(f"table is not allowed: {unexpected[0]}")

        return normalized

    def _extract_sql_tables(self, compact_sql: str) -> set[str]:
        tables: set[str] = set()
        for match in re.finditer(r"\b(?:from|join)\s+([`\"\[]?[\w.]+[`\"\]]?)", compact_sql):
            raw_name = match.group(1).strip("`\"[]")
            table_name = raw_name.split(".")[-1]
            tables.add(table_name)
        return tables

    async def _rows_to_resource_candidates(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ordered_ids = self._extract_resource_ids(rows)
        detail_by_id = await self._fetch_resource_details(ordered_ids) if ordered_ids else {}

        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            resource_id = self._row_resource_id(row)
            if resource_id:
                detail = detail_by_id.get(resource_id, {})
                merged = {**detail, **{k: v for k, v in row.items() if v is not None}}
                candidate = self._resource_row_to_candidate(merged)
            else:
                candidate = self._resource_row_to_candidate(row)

            if not candidate.get("id") and not candidate.get("title"):
                continue
            dedupe_key = candidate.get("id") or candidate.get("title")
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            candidates.append(candidate)

        for resource_id, detail in detail_by_id.items():
            if resource_id not in seen:
                candidates.append(self._resource_row_to_candidate(detail))

        return candidates

    def _extract_resource_ids(self, rows: list[dict[str, Any]]) -> list[str]:
        ids: list[str] = []
        seen: set[str] = set()
        for row in rows:
            resource_id = self._row_resource_id(row)
            if resource_id and resource_id not in seen:
                ids.append(resource_id)
                seen.add(resource_id)
        return ids

    def _row_resource_id(self, row: dict[str, Any]) -> str:
        value = row.get("id") or row.get("resource_id") or row.get("learning_resource_id")
        return str(value) if value else ""

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
            details = {
                str(row["id"]): self._serialize_row(dict(row))
                for row in detail_result.mappings().all()
            }

            tag_result = await session.execute(
                select(
                    ResourceKnowledge.resource_id,
                    KnowledgePoint.name.label("knowledge_name"),
                )
                .join(KnowledgePoint, ResourceKnowledge.kp_id == KnowledgePoint.id)
                .where(ResourceKnowledge.resource_id.in_(resource_ids))
            )
            for row in tag_result.mappings().all():
                resource_id = str(row["resource_id"])
                if resource_id not in details:
                    continue
                tags = details[resource_id].setdefault("knowledge_tags", [])
                if row["knowledge_name"] and row["knowledge_name"] not in tags:
                    tags.append(row["knowledge_name"])

        return {resource_id: details[resource_id] for resource_id in resource_ids if resource_id in details}

    def _resource_row_to_candidate(self, row: dict[str, Any]) -> dict[str, Any]:
        tags = row.get("knowledge_tags") or row.get("tags") or row.get("knowledge_name")
        return {
            "id": str(row.get("id") or row.get("resource_id") or ""),
            "type": str(row.get("type") or "article"),
            "title": str(row.get("title") or row.get("name") or "未命名资源"),
            "url": str(row.get("url") or ""),
            "difficulty": self._difficulty_label(row.get("difficulty") or row.get("difficult")),
            "time_needed_min": self._safe_int(row.get("time_needed_min") or row.get("time_need"), 0),
            "knowledge_tags": self._split_tags(tags),
            "recommend_reason": str(row.get("recommend_reason") or "由 SqlRetrievalTool 根据计划召回。"),
        }

    def _serialize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return {key: self._serialize_value(value) for key, value in row.items()}

    def _serialize_value(self, value: Any) -> Any:
        if isinstance(value, datetime | date):
            return value.isoformat()
        return value

    def _difficulty_label(self, value: Any) -> str:
        if isinstance(value, str) and value in {"初级", "中级", "高级"}:
            return value
        try:
            score = float(value)
        except (TypeError, ValueError):
            return "中级"
        if score <= 0.4:
            return "初级"
        if score >= 0.7:
            return "高级"
        return "中级"

    def _split_tags(self, value: Any) -> list[Any]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return self._as_list(value)

    def _dedupe_resources(self, resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in resources:
            if not isinstance(item, dict):
                continue
            key = str(item.get("id") or item.get("resource_id") or item.get("title") or item.get("name") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(dict(item))
        return deduped

    def _resource_time_needed(self, item: dict[str, Any]) -> int:
        value = self._safe_int(item.get("time_needed_min") or item.get("time_need"), 0)
        return value if value > 0 else 10**9

    def _resource_difficulty_score(self, item: dict[str, Any]) -> float:
        raw = item.get("difficult") or item.get("difficulty")
        if isinstance(raw, str):
            labels = {"初级": 0.3, "中级": 0.55, "高级": 0.85}
            if raw in labels:
                return labels[raw]
        return self._safe_float(raw, 0.55)

    def _difficulty_target(self, input_data: dict[str, Any]) -> float:
        raw = str(input_data.get("difficulty") or input_data.get("current_level") or "")
        if any(word in raw for word in ("初级", "基础", "简单", "低", "beginner", "easy")):
            return 0.3
        if any(word in raw for word in ("高级", "进阶", "挑战", "高", "advanced", "hard")):
            return 0.85
        return 0.55

    def _append_unique(self, values: list[str], item: str) -> None:
        if item not in values:
            values.append(item)

    def _force_pass_reflection(self, reflection_result: dict[str, Any]) -> dict[str, Any]:
        forced = dict(reflection_result)
        forced["passed"] = True
        forced["forced_pass"] = True
        forced.setdefault("suggestion", "已达到最大 reflection 次数，强制进入 summary。")
        return forced

    def _fallback_summary(
        self,
        plan: dict[str, Any],
        tool_results: dict[str, Any],
        reflection_result: dict[str, Any],
    ) -> dict[str, Any]:
        resources = tool_results.get("ranked_resources", [])
        if not plan.get("need_tool", False):
            text = plan.get("final_answer") or "我可以继续帮你查找或推荐学习资源。"
        elif resources:
            text = "已根据当前计划整理出推荐资源。"
        else:
            text = "推荐流程已跑通，具体资源等待真实工具接入后补全。"

        return {
            "recommendation_text": text,
            "planning": self._planning_from_plan(plan),
            "resources": resources,
            "rationale": plan.get("thought") or "资源推荐框架输出。",
            "sequence": [],
            "reflection": self._reflection_for_output(reflection_result),
            "tool_trace": tool_results.get("tool_trace", []),
            "query_results": tool_results.get("query_results", []),
            "candidate_store": tool_results.get("candidate_store", {}),
            "unmatched_candidate_items": tool_results.get("candidate_store", {}).get("unmatched_items", []),
        }

    def _planning_from_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        return {
            "recall_strategy": plan.get("recall_strategy", ""),
            "ranking_criteria": plan.get("ranking_criteria", []),
            "target_count": plan.get("target_count", 0),
        }

    def _reflection_for_output(self, reflection_result: dict[str, Any]) -> dict[str, Any]:
        return {
            "coverage_score": reflection_result.get("coverage_score", 0),
            "difficulty_match": reflection_result.get("difficulty_match", 0),
            "diversity_score": reflection_result.get("diversity_score", 0),
            "improvement_suggestion": reflection_result.get("suggestion", ""),
            "passed": reflection_result.get("passed", False),
            "forced_pass": reflection_result.get("forced_pass", False),
        }

    def _empty_tool_results(self) -> dict[str, Any]:
        return {
            "candidates": [],
            "query_results": [],
            "ranked_resources": [],
            "tool_trace": [],
            "candidate_store": self._empty_candidate_store_result(),
        }

    def _ensure_output_shape(self, output: dict[str, Any]) -> dict[str, Any]:
        resources = [
            self._normalize_resource(item)
            for item in output.get("resources", [])
            if isinstance(item, dict)
        ]
        recommendation_text = (
            output.get("recommendation_text")
            or output.get("response_text")
            or output.get("content")
            or "资源推荐框架已运行，具体资源待工具接入后补全。"
        )
        planning = output.get("planning") or {
            "recall_strategy": "",
            "ranking_criteria": [],
            "target_count": len(resources),
        }
        rationale = output.get("rationale") or "资源推荐框架输出。"
        sequence = output.get("sequence") or [f"学习《{item['title']}》" for item in resources]
        reflection = output.get("reflection") or {
            "coverage_score": 0,
            "difficulty_match": 0,
            "diversity_score": 0,
            "improvement_suggestion": "待接入真实推荐工具。",
        }
        tool_trace = output.get("tool_trace", [])
        query_results = [
            item for item in output.get("query_results", []) if isinstance(item, dict)
        ]
        candidate_store = self._normalize_candidate_store_result(output.get("candidate_store"))
        unmatched_candidate_items = [
            str(item)
            for item in self._as_list(
                output.get("unmatched_candidate_items")
                or candidate_store.get("unmatched_items")
            )
            if str(item).strip()
        ]

        resource_list = output.get("resource_list")
        if not isinstance(resource_list, dict):
            resource_list = {
                "resources": resources,
                "query_results": query_results,
                "planning": planning,
                "rationale": rationale,
                "sequence": sequence,
                "tool_trace": tool_trace,
            }
        resource_list["candidate_store"] = candidate_store
        resource_list["unmatched_candidate_items"] = unmatched_candidate_items

        text_for_next = str(recommendation_text)
        text_for_next = self._append_unmatched_candidate_notice(
            text_for_next,
            unmatched_candidate_items,
        )
        plan_history = [
            item for item in output.get("plan_history", []) if isinstance(item, dict)
        ]
        reflection_history = [
            item for item in output.get("reflection_history", []) if isinstance(item, dict)
        ]
        return {
            "recommendation_text": text_for_next,
            # Downstream adapters:
            # knowledge_responder reads this as resource context; direct successors can
            # also consume the text aliases without relying on graph-specific extraction.
            "response_text": str(output.get("response_text") or text_for_next),
            "content": str(output.get("content") or text_for_next),
            "raw_response": str(output.get("raw_response") or text_for_next),
            "final_response": str(output.get("final_response") or text_for_next),
            "resource_list": resource_list,
            "query_results": query_results,
            "planning": planning,
            "resources": resources,
            "rationale": rationale,
            "sequence": sequence,
            "reflection": reflection,
            "tool_trace": tool_trace,
            "candidate_store": candidate_store,
            "unmatched_candidate_items": unmatched_candidate_items,
            "plan_history": plan_history,
            "reflection_history": reflection_history,
        }

    def _normalize_candidate_store_result(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return self._empty_candidate_store_result()
        normalized = self._empty_candidate_store_result()
        for key in ("requested_items", "matched_items", "unmatched_items", "matched_resource_ids"):
            normalized[key] = [
                str(item)
                for item in self._as_list(value.get(key))
                if str(item).strip()
            ]
        normalized["matches"] = [
            item
            for item in self._as_list(value.get("matches"))
            if isinstance(item, dict)
        ]
        return normalized

    def _append_unmatched_candidate_notice(self, text: str, unmatched_items: list[str]) -> str:
        if not unmatched_items:
            return text
        missing = [item for item in unmatched_items if item and item not in text]
        if not missing:
            return text
        separator = "\n\n" if text else ""
        return f"{text}{separator}另外，以下候选资源未在资源库中匹配到：{', '.join(missing)}。"

    def _normalize_resource(self, item: dict[str, Any]) -> dict[str, Any]:
        resource = {
            "id": str(item.get("id") or item.get("resource_id") or ""),
            "type": str(item.get("type") or "article"),
            "title": str(item.get("title") or item.get("name") or "未命名资源"),
            "url": str(item.get("url") or ""),
            "difficulty": str(item.get("difficulty") or "中级"),
            "time_needed_min": self._safe_int(item.get("time_needed_min") or item.get("time_need"), 0),
            "knowledge_tags": self._as_list(item.get("knowledge_tags") or item.get("tags")),
            "recommend_reason": str(item.get("recommend_reason") or "待真实工具补充推荐理由。"),
        }
        if item.get("rank") is not None:
            resource["rank"] = self._safe_int(item.get("rank"), 0)
        if item.get("ctr_score") is not None:
            resource["ctr_score"] = self._safe_float(item.get("ctr_score"), 0)
        if item.get("similarity_score") is not None:
            resource["similarity_score"] = self._safe_float(item.get("similarity_score"), 0)
        if item.get("similarity_reason") is not None:
            resource["similarity_reason"] = str(item.get("similarity_reason") or "")
        if item.get("source_items") is not None:
            resource["source_items"] = self._as_list(item.get("source_items"))
        return resource

    def _safe_int(self, value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _safe_float(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _count_tool_result(self, result: Any) -> int:
        if isinstance(result, list | tuple | set | dict):
            return len(result)
        return 0 if result is None else 1

    def _as_list(self, value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, (tuple, set)):
            return list(value)
        return [value] if value else []

    def _merge_usage(self, total: dict[str, Any], usage: dict[str, Any]) -> None:
        for key, value in usage.items():
            if isinstance(value, int | float):
                total[key] = total.get(key, 0) + value
            else:
                total[key] = value

    def _normalize_tool_name(self, name: str) -> str:
        aliases = {
            "candidate_store_tool": "CandidateStoreTool",
            "query_tool": "QueryTool",
            "sql_retrieval_tool": "SqlRetrievalTool",
            "item_cf_retrieval_tool": "ItemCfRetrievalTool",
            "ranking_tool": "RankingTool",
        }
        return aliases.get(name, name)

    def _trace(self, message: str, *args: Any) -> None:
        try:
            from app.services.trace_logger import get_trace_logger

            get_trace_logger().debug(message, *args)
        except Exception:
            logger.debug(message, *args)
