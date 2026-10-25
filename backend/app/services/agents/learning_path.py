"""Learning Path Agent backed by the native LPP Runtime."""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.services.agents.base_agent import BaseAgent
from app.services.kt_integration import resolve_kt_student_id
from app.services.topic_retrieval import retrieve_topic_knowledge, prepare_topic_explanation_input, related_topic_retrieval
from app.services.lpp_integration import (
    build_diagnosis_prompt_context,
    build_learning_profile_prompt_context,
    build_learning_path_fields,
    build_lpp_prompt_context,
    build_relevant_knowledge_graph_prompt_context,
    extract_explicit_target_question,
    lpp_prompt_skill_ids,
    run_lpp_for_student,
    skill_priorities_from_diagnosis,
    validate_lpp_topic_scope,
)


class LearningPathAgent(BaseAgent):
    config_file = "learning_path"

    async def execute(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        if not settings.lpp.enabled:
            return await super().execute(input_data, context)

        student_id = resolve_kt_student_id(input_data, context)
        if not student_id:
            return self._unavailable_result("未找到可用的 LPP 学生编号")

        diagnosis = input_data.get("diagnosis_result") or {}
        if not isinstance(diagnosis, dict):
            diagnosis = {}
        previous_retrieval = diagnosis.get("knowledge_retrieval") or {}
        same_turn = bool(context.get("turn_id")) and previous_retrieval.get("source_turn_id") == context.get("turn_id")
        if previous_retrieval.get("status") == "ok" and previous_retrieval.get("matches") and same_turn:
            retrieval = previous_retrieval
        else:
            retrieval = await retrieve_topic_knowledge(input_data, llm=self.llm)
            retrieval = {**retrieval, "source_turn_id": context.get("turn_id")}
            # A previous diagnosis is not current topic evidence merely because
            # it exists in the checkpoint or the learner's profile.
            diagnosis = {}
        retrieval = related_topic_retrieval(retrieval)
        allowed_diagnosis_ids = {str(m['skill_id']) for m in retrieval.get('matches', [])}
        diagnosis = {
            **diagnosis,
            'knowledge_states': [s for s in diagnosis.get('knowledge_states', []) if str(s.get('skill_id')) in allowed_diagnosis_ids],
            'weak_points': [s for s in diagnosis.get('weak_points', []) if isinstance(s, dict) and str(s.get('skill_id')) in allowed_diagnosis_ids],
            'mastery_rates': {k: v for k, v in (diagnosis.get('mastery_rates') or {}).items() if str(k) in allowed_diagnosis_ids},
            'knowledge_retrieval': retrieval,
        }
        if retrieval.get("status") != "ok" or len(retrieval.get("matches") or []) < 5:
            return self._unavailable_result(
                retrieval.get("message") if retrieval.get("status") != "ok"
                else "当前主题的相关知识点不足五个，无法生成五阶段路径；不会用其他主题补齐。",
                retrieval,
            )
        role_order = {"safety_ethics": 0, "prerequisite": 1, "core": 2, "application": 3}
        matches = sorted(retrieval["matches"], key=lambda item: role_order.get(item["role"], 4))
        topic_skill_ids = [int(item["skill_id"]) for item in matches]
        allowed = set(topic_skill_ids)
        core_ids = [int(item['skill_id']) for item in retrieval['matches'] if item['role'] == 'core']
        preferred_skill_ids = [sid for sid in skill_priorities_from_diagnosis(diagnosis) if sid in set(core_ids)]
        if not preferred_skill_ids:
            preferred_skill_ids = core_ids or topic_skill_ids
        target_question_id = extract_explicit_target_question(input_data)
        runtime = await run_lpp_for_student(
            student_id,
            target_question_id=target_question_id,
            preferred_skill_ids=preferred_skill_ids,
            topic_skill_ids=topic_skill_ids,
        )
        if runtime is None:
            return self._unavailable_result("当前主题下没有可用的五阶段规划，请检查题库覆盖或稍后重试。", retrieval)
        try:
            validate_lpp_topic_scope(runtime.data, topic_skill_ids)
        except (TypeError, ValueError):
            return self._unavailable_result("规划结果超出本轮学习主题，已停止返回不相关路线。", retrieval)

        enriched_input = prepare_topic_explanation_input(input_data, retrieval)
        enriched_input.setdefault(
            "goal",
            enriched_input.get("current_message") or "完成本次个性化学习路径",
        )
        enriched_input["diagnosis_result"] = diagnosis
        enriched_input["knowledge_retrieval"] = retrieval
        enriched_input["topic_context"] = {key: value for key, value in retrieval.get("topic_context", {}).items() if key != "original_query"}
        enriched_input["retrieval_queries"] = retrieval.get("queries", {})
        enriched_input["relevance_matches"] = retrieval["matches"]
        enriched_input["lpp_runtime"] = runtime.data
        execution_context = {
            **context,
            "kt_student_id": student_id,
            "_lpp_runtime": runtime,
            "_knowledge_retrieval": retrieval,
        }
        result = await super().execute(enriched_input, execution_context)
        result["lpp_integrated"] = True
        return result

    async def enrich_input(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Apply the strict LLM boundary after profile enrichment."""
        enriched = await super().enrich_input(input_data, context)
        diagnosis = enriched.get("diagnosis_result") or {}
        if not isinstance(diagnosis, dict):
            diagnosis = {}
        runtime = enriched.get("lpp_runtime") or {}
        if not isinstance(runtime, dict):
            runtime = {}
        profile = enriched.get("user_profile") or {}
        if not isinstance(profile, dict):
            profile = {}
        graph = diagnosis.get("knowledge_graph") or enriched.get("knowledge_graph") or {}
        if not isinstance(graph, dict):
            graph = {}

        skill_ids = lpp_prompt_skill_ids(runtime)
        enriched["diagnosis_result"] = build_diagnosis_prompt_context(diagnosis)
        enriched["user_profile"] = build_learning_profile_prompt_context(profile)
        enriched["knowledge_graph"] = build_relevant_knowledge_graph_prompt_context(
            graph,
            skill_ids,
        )
        enriched["lpp_runtime"] = build_lpp_prompt_context(runtime)
        return enriched

    def _unavailable_result(self, reason: str, retrieval: dict | None = None) -> dict[str, Any]:
        output = {
            "planning_rationale": reason,
            "learning_path": [],
            "stages": [],
            "total_estimated_time": "不可用",
            "estimated_completion": "不可用",
            "adaptive_rules": reason,
            "main_path_sequence": [],
            "optional_branch": [],
            "milestones": [],
            "path_adjustment_triggers": {
                "accelerate": "LPP 可用后重新评估",
                "remediate": "LPP 可用后重新评估",
                "redirect": "LPP 可用后重新评估",
            },
            "recommended_knowledge_points": [],
            "lpp_source": "lpp_unavailable",
        }
        if retrieval is not None:
            output["knowledge_retrieval"] = retrieval
            output["topic_context"] = retrieval.get("topic_context", {})
        return {
            "agent": self.name,
            "output": output,
            "usage": {},
            "latency_ms": 0,
            "lpp_integrated": False,
        }

    async def finalize_output(
        self,
        output: dict,
        input_data: dict,
        context: dict,
    ) -> dict:
        runtime = context.get("_lpp_runtime")
        if runtime is None:
            return output

        output = dict(output)
        output.update(build_learning_path_fields(runtime.data))
        retrieval = context.get("_knowledge_retrieval")
        if isinstance(retrieval, dict):
            output["knowledge_retrieval"] = retrieval
            output["topic_context"] = retrieval.get("topic_context", {})
            by_id = {str(item["skill_id"]): item for item in retrieval["matches"]}
            for stage in output["learning_path"]:
                for skill in stage["skills"]:
                    skill["reason"] = by_id[skill["skill_id"]]["reason"]
                    skill["relevance_role"] = by_id[skill["skill_id"]]["role"]
            # A free-form rationale can silently contradict the fixed stages.
            # Bind the explanation to the actual sequence and reviewed links.
            output["planning_rationale"] = "围绕本轮学习主题，按以下五阶段推进：" + "；".join(
                f'{stage["name"]}：' + "、".join(skill["reason"] for skill in stage["skills"])
                for stage in output["learning_path"]
            ) + "。"
            import copy
            output["stages"] = copy.deepcopy(output["learning_path"])
        output.setdefault(
            "planning_rationale",
            "按照 LPP Runtime 给出的 P1 至 P5 固定知识点顺序完成学习。",
        )
        output.setdefault(
            "adaptive_rules",
            "每题完成后检查对应知识点；未达到检查点时先补充讲解再继续。",
        )
        output.setdefault(
            "path_adjustment_triggers",
            {
                "accelerate": "连续正确且能解释判断依据",
                "remediate": "答错或无法解释对应知识点",
                "redirect": "学习目标或目标题发生变化",
            },
        )
        return output
