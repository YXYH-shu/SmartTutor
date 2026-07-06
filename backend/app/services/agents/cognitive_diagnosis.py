"""Cognitive Diagnosis Agent – knowledge mastery assessment.

集成模式(integrated)下:先调用 kt-runtime-skill 拿真实掌握度,LLM 只生成认知归因。
其他模式(off/standalone):走纯 LLM 模拟,与 main 行为一致。

Post-processes by updating the user's knowledge_graph and weak_points
in their UserProfile.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.user_profile import UserProfile
from app.services.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class CognitiveDiagnosisAgent(BaseAgent):
    config_file = "cognitive_diagnosis"

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
            student_id = input_data.get("student_id") or context.get("student_id")
            if student_id:
                kt_result = await self._run_kt_diagnosis(str(student_id), input_data, context)
                if kt_result is not None:
                    return await self._merge_kt_with_llm(kt_result, input_data, context)
                # KT 失败
                if not settings.kt.fallback_to_llm:
                    raise RuntimeError(
                        f"KT diagnosis failed and fallback_to_llm=False for student {student_id}"
                    )
                logger.warning("KT failed — falling back to LLM-only diagnosis")

        return await super().execute(input_data, context)

    async def _run_kt_diagnosis(
        self,
        student_id: str,
        input_data: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        """调用 KT integration 拿真实诊断数据。返回 None 表示失败。"""
        from app.services.kt_integration import run_kt_for_student

        initial_query = input_data.get("current_message") or input_data.get("goal", "")
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
        # 把 KT 数据塞进 input,prompt 模板未来可读取以引导 LLM 只做归因
        enriched_input = dict(input_data)
        enriched_input["kt_predictions"] = kt_result["knowledge_states"]
        enriched_input["kt_mastery_rates"] = kt_result["mastery_rates"]
        enriched_input["kt_weak_points"] = kt_result["weak_points"]

        # 走父类完整流程:enrich → render → LLM → validate → log → post_process
        base_result = await super().execute(enriched_input, context)

        # 强制覆盖:KT 是 ground truth,LLM 不能改写数值
        output = dict(base_result.get("output") or {})
        output["knowledge_states"] = kt_result["knowledge_states"]
        output["mastery_rates"] = kt_result["mastery_rates"]
        output["weak_points"] = kt_result["weak_points"]
        output["diagnosis_source"] = "kt_rekt"
        output["kt_metrics"] = kt_result.get("metrics", {})
        output["kt_model_info"] = kt_result.get("model_info", {})
        if kt_result.get("llm_analysis"):
            output["kt_llm_analysis"] = kt_result["llm_analysis"]

        base_result["output"] = output
        base_result["kt_integrated"] = True
        return base_result

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
                    mastery = ks.get("mastery_percent", "0%")
                    if isinstance(mastery, str):
                        try:
                            prob = int(mastery.replace("%", "")) / 100.0
                        except ValueError:
                            prob = 0.0
                    else:
                        prob = float(mastery) if mastery else 0.0
                    existing[skill_id] = prob
                profile.knowledge_graph = existing

            # Persist structured knowledge graph from diagnosis output
            kg_output = output.get("knowledge_graph")
            if kg_output and isinstance(kg_output, dict):
                existing = profile.knowledge_graph or {}
                if isinstance(existing, dict):
                    existing["_graph"] = kg_output
                    profile.knowledge_graph = existing

            # Update weak points
            weak = output.get("weak_points", [])
            if weak:
                profile.weak_points = weak

            profile.last_diagnosis = datetime.now(timezone.utc)
            session.add(profile)
            await session.commit()
            logger.info("Updated UserProfile for user %s after diagnosis", user_id)
