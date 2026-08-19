"""Learning Path Agent backed by the native LPP Runtime."""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.services.agents.base_agent import BaseAgent
from app.services.kt_integration import resolve_kt_student_id
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
        preferred_skill_ids = skill_priorities_from_diagnosis(diagnosis)
        target_question_id = extract_explicit_target_question(input_data)
        runtime = await run_lpp_for_student(
            student_id,
            target_question_id=target_question_id,
            preferred_skill_ids=preferred_skill_ids,
        )
        if runtime is None:
            return self._unavailable_result("LPP Skill 本次运行失败，请稍后重试")

        enriched_input = dict(input_data)
        enriched_input.setdefault(
            "goal",
            enriched_input.get("current_message") or "完成本次个性化学习路径",
        )
        enriched_input["diagnosis_result"] = diagnosis
        enriched_input["lpp_runtime"] = runtime.data
        execution_context = {
            **context,
            "kt_student_id": student_id,
            "_lpp_runtime": runtime,
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

    def _unavailable_result(self, reason: str) -> dict[str, Any]:
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
