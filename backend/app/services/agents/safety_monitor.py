"""Safety Monitor Agent facade for the three-branch SafetyPipeline."""

from __future__ import annotations

from typing import Any

from app.services.agents.base_agent import BaseAgent
from app.services.safety_guidance_skill import SafetyGuidanceSkill
from app.services.safety_pipeline import SafetyPipeline


class SafetyMonitorAgent(BaseAgent):
    config_file = "safety_monitor"

    def __init__(self, llm=None) -> None:
        super().__init__(llm=llm)
        self._pipeline = SafetyPipeline(
            llm=self.llm,
            guidance_skill=SafetyGuidanceSkill(llm=self.llm),
        )

    async def execute(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = str(
            input_data.get("raw_text")
            or input_data.get("current_message")
            or input_data.get("message")
            or ""
        )
        grade = str(
            input_data.get("student_grade")
            or input_data.get("grade_level")
            or input_data.get("user_age")
            or "未知"
        )
        recent = input_data.get("recent_messages") or []
        result = await self._pipeline.execute(
            query=query,
            student_grade=grade,
            conversation_context="\n".join(str(item) for item in recent[-6:]),
        )
        return {
            "agent": self.name,
            "output": {
                "branch": result.branch,
                "reject_type": result.reject_type,
                "safe_query": result.safe_query,
                "learning_options": result.learning_options or [],
                "recommended_option": result.recommended_option,
                "direct_response": result.direct_response,
                "safety_context": result.safety_context or {},
            },
            "usage": {},
            "latency_ms": 0,
        }
