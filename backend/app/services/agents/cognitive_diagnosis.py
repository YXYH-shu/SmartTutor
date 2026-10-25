"""Cognitive Diagnosis Agent – knowledge mastery assessment.

集成模式(integrated)下:先调用 kt-runtime-skill 拿真实掌握度,LLM 只生成认知归因。
其他模式(off/standalone):走纯 LLM 模拟,与 main 行为一致。

Post-processes by updating the user's knowledge_graph and weak_points
in their UserProfile.
"""

from __future__ import annotations

import logging
import copy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.user_profile import UserProfile
from app.services.agents.base_agent import BaseAgent
from app.services.topic_retrieval import retrieve_topic_knowledge, prepare_topic_explanation_input, related_topic_retrieval

logger = logging.getLogger(__name__)


class CognitiveDiagnosisAgent(BaseAgent):
    config_file = "cognitive_diagnosis"

    @staticmethod
    def _mastery_probability(knowledge_state: dict[str, Any]) -> float:
        """Normalize a KT mastery value to a probability in [0, 1]."""
        raw_rate = knowledge_state.get("mastery_rate")
        if raw_rate is not None:
            try:
                return max(0.0, min(1.0, float(raw_rate)))
            except (TypeError, ValueError):
                pass

        raw_percent = knowledge_state.get("mastery_percent", 0)
        try:
            if isinstance(raw_percent, str):
                value = float(raw_percent.strip().removesuffix("%")) / 100.0
            else:
                value = float(raw_percent)
            return max(0.0, min(1.0, value))
        except (TypeError, ValueError):
            return 0.0

    async def execute(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """根据 settings.kt.mode 选择执行路径。

        - integrated: 优先调 KT 拿真实掌握度,LLM 做归因,失败可降级
        - off/standalone: 走 BaseAgent 默认 LLM 路径
        """
        context = context or {}

        if settings.kt.mode == "integrated":
            from app.services.kt_integration import resolve_kt_student_id

            student_id = resolve_kt_student_id(input_data, context)
            if not student_id:
                return self._unavailable_result("未找到可用的 KT 学生编号")

            retrieval = await retrieve_topic_knowledge(input_data, llm=self.llm, fill_to_limit=True)
            retrieval = {**retrieval, "source_turn_id": context.get("turn_id")}
            if retrieval.get("status") != "ok" or not retrieval.get("matches"):
                return self._unavailable_result(
                    retrieval.get("message") or "当前主题没有可用的相关知识点", retrieval,
                )
            topic_input = prepare_topic_explanation_input(input_data, retrieval)
            topic_input["knowledge_retrieval"] = retrieval
            topic_input["topic_context"] = retrieval["topic_context"]
            topic_input["targets"] = ",".join(str(item["skill_id"]) for item in retrieval["matches"])
            topic_input["history_context"] = "；".join(
                query for queries in retrieval["queries"].values() for query in queries
            )
            kt_result = await self._run_kt_diagnosis(student_id, topic_input, context)
            if kt_result is not None:
                kt_result = self._bind_topic_facts(kt_result, retrieval)
                if not kt_result["knowledge_states"]:
                    return self._unavailable_result("当前主题没有可用的 KT 预测结果", retrieval)
                if len(kt_result['knowledge_states']) != len(retrieval['matches']):
                    return self._unavailable_result('部分知识点缺少真实 KT 预测，暂不能返回完整诊断。', retrieval)
                execution_context = {
                    **context, "kt_student_id": student_id, "_knowledge_retrieval": retrieval,
                }
                return await self._merge_kt_with_llm(
                    kt_result,
                    topic_input,
                    execution_context,
                )
            # Topic membership is not evidence of mastery. Never synthesize
            # learner probabilities when the topic-scoped KT worker failed.
            return self._unavailable_result("当前主题的 KT 推理不可用，请稍后重试", retrieval)

        return await super().execute(input_data, context)

    def _unavailable_result(self, reason: str, retrieval: dict | None = None) -> dict[str, Any]:
        result = {
            "agent": self.name,
            "output": {
                "topic_analysis": reason,
                "knowledge_states": [],
                "mastery_rates": {},
                "cognitive_attribution": {"root_causes": []},
                "weak_points": [],
                "diagnosis_summary": reason,
                "recommended_actions": [],
                "knowledge_graph": {"nodes": [], "edges": []},
                "diagnosis_source": "kt_unavailable",
                "kt_metrics": {},
                "kt_model_info": {},
            },
            "usage": {},
            "latency_ms": 0,
            "kt_integrated": False,
        }
        if retrieval is not None:
            result["output"]["knowledge_retrieval"] = retrieval
            result["output"]["topic_context"] = retrieval.get("topic_context", {})
        return result

    @staticmethod
    def _bind_topic_facts(kt_result: dict, retrieval: dict) -> dict:
        """Keep model probabilities only for closed-catalog semantic matches."""
        result = copy.deepcopy(kt_result)
        by_id = {str(row.get("skill_id")): row for row in result.get("knowledge_states", [])}
        states = []
        for rank, match in enumerate(retrieval["matches"], 1):
            row = by_id.get(str(match["skill_id"]))
            if row is None:
                continue
            states.append({
                **row, "skill_name": match["skill_name"],
                "relevance_role": match["role"], "relevance_reason": match["reason"],
                "relevance_rank": match.get("relevance_rank", rank),
                "relevance_tier": match.get("relevance_tier", "related"),
            })
        result["knowledge_states"] = states
        result["mastery_rates"] = {row["skill_id"]: row["mastery_rate"] for row in states}
        result["weak_points"] = [row for row in states if row.get("status") == "weak"]
        analysis = result.get("llm_analysis")
        if isinstance(analysis, dict):
            analysis["selection_method"] = {
                "name": retrieval["method"], "selected_count": len(states),
                "description": "按语义相关度排序；已复核主题相关点在前，弱关联拓展补充点在后。",
            }
            points = {str(point.get("source_skill_id")): point for point in analysis.get("selected_knowledge_points", [])}
            analysis["selected_knowledge_points"] = [points[row["skill_id"]] for row in states if row["skill_id"] in points]
        return result

    async def _run_kt_diagnosis(
        self,
        student_id: str,
        input_data: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        """调用 KT integration 拿真实诊断数据。返回 None 表示失败。"""
        from app.services.kt_integration import run_kt_for_student

        topic = input_data.get("topic_context") or {}
        initial_query = topic.get("safe_query") or topic.get("current_query") or input_data.get("current_message") or input_data.get("goal", "")
        history_context = input_data.get("history_context")
        targets = input_data.get("targets") or context.get("targets")

        return await run_kt_for_student(
            student_id=student_id,
            targets=targets,
            initial_query=initial_query,
            history_context=history_context,
        )

    async def _merge_kt_with_llm(
        self,
        kt_result: dict[str, Any],
        input_data: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """KT 数据 + LLM 归因。

        KT 提供的数值(mastery_rates、knowledge_states、weak_points)是 ground truth,
        LLM 输出的同名字段会被强制覆盖。LLM 仅在 cognitive_attribution / summary 等
        自然语言字段上有创作权。
        """
        from app.services.kt_integration import build_kt_prompt_context

        # Runtime 保留完整事实；Prompt 只消费有界投影，避免重复传输数百条状态。
        enriched_input = dict(input_data)
        enriched_input.pop("kt_predictions", None)
        enriched_input.pop("kt_mastery_rates", None)
        enriched_input.pop("kt_weak_points", None)
        retrieval = context.get("_knowledge_retrieval") or {}
        related = related_topic_retrieval(retrieval)
        ids = {str(m['skill_id']) for m in related['matches']}
        prompt_facts = {
            **kt_result,
            'knowledge_states': [s for s in kt_result.get('knowledge_states', []) if str(s.get('skill_id')) in ids],
        }
        enriched_input["kt_context"] = build_kt_prompt_context(prompt_facts)
        enriched_input["topic_context"] = {
            key: value for key, value in retrieval.get("topic_context", {}).items()
            if key != "original_query"
        }
        enriched_input["retrieval_queries"] = retrieval.get("queries", {})
        enriched_input["relevance_matches"] = related['matches']

        execution_context = {**context, "_kt_result": kt_result}
        base_result = await super().execute(enriched_input, execution_context)
        base_result["kt_integrated"] = True
        return base_result

    async def finalize_output(
        self,
        output: dict,
        input_data: dict,
        context: dict,
    ) -> dict:
        """Reapply KT ground truth before logging and profile persistence."""
        kt_result = context.get("_kt_result")
        if not isinstance(kt_result, dict):
            return output

        output = dict(output)
        output["knowledge_states"] = kt_result["knowledge_states"]
        output["mastery_rates"] = kt_result["mastery_rates"]
        output["weak_points"] = kt_result["weak_points"]
        output["diagnosis_source"] = "kt"
        output["kt_metrics"] = kt_result.get("metrics", {})
        output["kt_model_info"] = kt_result.get("model_info", {})
        output["kt_student_id"] = context.get("kt_student_id")
        retrieval = context.get("_knowledge_retrieval")
        if isinstance(retrieval, dict):
            output["knowledge_retrieval"] = retrieval
            output["topic_context"] = retrieval.get("topic_context", {})
            if retrieval.get('selection_policy') == 'ranked_fixed_count':
                related_count = sum(s.get('relevance_tier') != 'extended' for s in output['knowledge_states'])
                extended_count = len(output['knowledge_states']) - related_count
                scope_note = f"本轮按相关度展示{len(output['knowledge_states'])}个知识点，前{related_count}个为主题相关点，后{extended_count}个为拓展补充。"
                output['diagnosis_summary'] = scope_note + str(output.get('diagnosis_summary') or '')
        if kt_result.get("llm_analysis"):
            output["kt_llm_analysis"] = kt_result["llm_analysis"]
        return output

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

            # The normalized KT result is already the skill-selected Top-18.
            # Replace prior state so an old full prediction cannot leak back
            # into graph context for later agents.
            knowledge_states = output.get("knowledge_states", [])
            profile.knowledge_graph = {
                str(ks.get("skill_id") or ks.get("skill_name")): self._mastery_probability(ks)
                for ks in knowledge_states
                if isinstance(ks, dict) and (ks.get("skill_id") or ks.get("skill_name"))
            }

            # Persist only this round's structured knowledge graph.
            kg_output = output.get("knowledge_graph")
            if kg_output and isinstance(kg_output, dict):
                profile.knowledge_graph["_graph"] = kg_output

            # Empty is meaningful: it clears stale weak points from older runs.
            profile.weak_points = list(output.get("weak_points") or [])

            profile.last_diagnosis = datetime.now(timezone.utc)
            session.add(profile)
            await session.commit()
            logger.info("Updated UserProfile for user %s after diagnosis", user_id)
