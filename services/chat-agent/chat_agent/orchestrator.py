from __future__ import annotations
from typing import Any

from chat_agent.models import OrchestrationResult
from chat_agent.models import RouterDecision
from chat_agent.router import RuleBasedRouter
from chat_agent.session import ChatSession
from chat_agent.skill_registry import SkillRegistry
from chat_agent.validator import SkillExecutionValidator


class Orchestrator:
    def __init__(
        self,
        registry: SkillRegistry,
        router: RuleBasedRouter,
        validator: SkillExecutionValidator,
    ):
        self.registry = registry
        self.router = router
        self.validator = validator

    def handle_message(self, message: str, session: ChatSession | None = None) -> OrchestrationResult:
        active_session = session or ChatSession()
        active_session.add_message("user", message)
        active_session.add_event("message_received", "收到用户消息。", user_message=message)

        if active_session.pending_skill == "kt-runtime-skill" and self.router.is_cancel(message):
            active_session.clear_pending()
            result = OrchestrationResult(
                status="cancelled",
                final_response="已取消当前 KT 分析请求。",
                skill_name=None,
                raw_result=None,
            )
            active_session.add_message("assistant", result.final_response)
            active_session.last_result = result
            active_session.add_event("workflow_finished", "已取消当前 KT 分析请求。", status=result.status)
            return result

        decision = self.router.route(message)
        if not decision.skill_name and active_session.pending_skill == "kt-runtime-skill":
            decision = self._continue_pending_kt(message, active_session)

        if not decision.skill_name:
            result = OrchestrationResult(
                status="no_skill",
                final_response="没有找到适合处理该请求的 skill。",
                skill_name=None,
                raw_result=None,
            )
            active_session.add_message("assistant", result.final_response)
            active_session.last_result = result
            active_session.add_event("workflow_finished", "没有找到匹配的 skill。", status=result.status)
            return result

        active_session.add_event("skill_selected", f"选择 skill：{decision.skill_name}", skill_name=decision.skill_name)
        active_session.update_slots(decision.inputs)
        for key, value in decision.inputs.items():
            active_session.add_event("slot_filled", f"已收集参数：{key}", slot=key, value=value)

        skill = self.registry.get_skill(decision.skill_name)
        merged_inputs = dict(active_session.slots)
        missing_inputs = self.router.missing_kt_inputs(merged_inputs, skill.policy.required_inputs)

        if missing_inputs:
            active_session.pending_skill = decision.skill_name
            active_session.pending_inputs = list(missing_inputs)
            active_session.add_event("slot_missing", "参数不足，等待用户补充。", missing_inputs=missing_inputs)
            result = OrchestrationResult(
                status="need_input",
                final_response=self._missing_input_message(missing_inputs),
                skill_name=decision.skill_name,
                raw_result=None,
                missing_inputs=missing_inputs,
            )
            active_session.add_message("assistant", result.final_response)
            active_session.last_result = result
            return result

        active_session.clear_pending()
        active_session.add_event("skill_execution_started", "开始按 SKILL.md 执行 skill。", skill_name=decision.skill_name)
        skill_result = self.registry.run_skill(decision.skill_name, merged_inputs, session=active_session)
        active_session.add_event("skill_execution_finished", "SKILL.md 执行完成。", skill_name=decision.skill_name)
        active_session.add_event(
            "skill_result",
            "skill 返回结果。",
            skill_name=decision.skill_name,
            status=str(skill_result.raw_json.get("status", "ok")),
            metrics=skill_result.metrics,
            raw_result=skill_result.raw_json,
            report_markdown=skill_result.report_markdown or "",
        )
        self.validator.validate(
            skill=skill,
            executor_name=skill_result.executor_name,
            command=None,
            output=skill_result.raw_json,
        )
        active_session.add_event("validation_passed", "skill 输出校验通过。", skill_name=decision.skill_name)

        result = OrchestrationResult(
            status="ok",
            final_response=skill_result.report_markdown or "",
            skill_name=decision.skill_name,
            raw_result=skill_result.raw_json,
        )
        active_session.add_message("assistant", result.final_response)
        active_session.last_result = result
        active_session.add_event("workflow_finished", "工作流执行完成。", status=result.status)
        return result

    def _continue_pending_kt(self, message: str, session: ChatSession) -> RouterDecision:
        inputs = self.router.extract_kt_inputs(
            message,
            allow_message_as_context=True,
            allow_bare_student_id=True,
            expected_inputs=session.pending_inputs,
        )
        if not inputs:
            session.clear_pending()
            return RouterDecision(skill_name=None, reason="Pending KT reply did not contain requested inputs")

        merged_inputs = dict(session.slots)
        merged_inputs.update(inputs)
        skill = self.registry.get_skill(session.pending_skill)
        return RouterDecision(
            skill_name="kt-runtime-skill",
            inputs=inputs,
            missing_inputs=self.router.missing_kt_inputs(merged_inputs, skill.policy.required_inputs),
            reason="Continue pending KT request",
        )

    def _missing_input_message(self, missing_inputs: list[str]) -> str:
        if missing_inputs == ["student_id"]:
            return "请补充学生 ID。"
        return "请补充缺少的 skill 输入：" + "、".join(missing_inputs) + "。"
