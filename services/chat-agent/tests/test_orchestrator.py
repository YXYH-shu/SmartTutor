import pytest

from chat_agent.models import SkillExecutionResult, SkillDefinition, SkillPolicy
from chat_agent.orchestrator import Orchestrator
from chat_agent.router import RuleBasedRouter
from chat_agent.skill_registry import SkillRegistry
from chat_agent.validator import SkillExecutionValidator, ValidationError


class FakeSkillExecutor:
    name = "skill_markdown"

    def __init__(self):
        self.inputs = None

    def run(self, skill, inputs, session=None):
        self.inputs = dict(inputs)
        return SkillExecutionResult(
            skill_name="kt-runtime-skill",
            executor_name=self.name,
            raw_json={"llm_analysis": {"report_markdown": "报告正文"}},
            report_markdown="报告正文",
            predictions=[],
            metrics={},
            command_results=[],
        )


def kt_skill():
    return SkillDefinition(
        name="kt-runtime-skill",
        description="Use when 需要基于学生 ID 运行 KT 学情分析。",
        path=None,
        instructions="默认用 conda run -n kt python scripts/run_kt.py\n不要写临时 Python 脚本",
        policy=SkillPolicy(
            default_entrypoints=["conda run -n kt python scripts/run_kt.py"],
            required_inputs=["student_id"],
            forbidden_actions=["不要写临时 Python 脚本"],
            output_paths=["llm_analysis.report_markdown"],
        ),
        level=1,
        executor_name="skill_markdown",
    )


def test_router_identifies_kt_request_and_extracts_slots():
    router = RuleBasedRouter()

    decision = router.route("帮学生 5 做 KT 学情分析。学生最近在学电路。")

    assert decision.skill_name == "kt-runtime-skill"
    assert decision.inputs["student_id"] == "5"
    assert decision.inputs["history_context"] == "学生最近在学电路。"
    assert decision.missing_inputs == []


def test_router_does_not_require_history_context():
    router = RuleBasedRouter()

    decision = router.route("帮学生 5 做 KT 学情分析")

    assert decision.skill_name == "kt-runtime-skill"
    assert decision.inputs["student_id"] == "5"
    assert decision.missing_inputs == []


def test_router_extracts_student_id_phrase():
    router = RuleBasedRouter()

    inputs = router.extract_kt_inputs("学生 ID 是 5。", expected_inputs=["student_id"], allow_bare_student_id=True)

    assert inputs == {"student_id": "5"}


def test_router_does_not_run_kt_for_capability_question():
    router = RuleBasedRouter()

    decision = router.route("你能做学情分析吗？")

    assert decision.skill_name is None
    assert decision.missing_inputs == []


def test_orchestrator_runs_skill_executor_with_student_id_only_and_returns_report():
    skill_executor = FakeSkillExecutor()
    registry = SkillRegistry(skill_executor=skill_executor)
    registry.register(kt_skill())
    orchestrator = Orchestrator(registry=registry, router=RuleBasedRouter(), validator=SkillExecutionValidator())

    result = orchestrator.handle_message("帮学生 5 做 KT 学情分析。")

    assert result.status == "ok"
    assert result.final_response == "报告正文"
    assert skill_executor.inputs == {"student_id": "5"}


def test_orchestrator_records_skill_result_event():
    skill_executor = FakeSkillExecutor()
    registry = SkillRegistry(skill_executor=skill_executor)
    registry.register(kt_skill())
    orchestrator = Orchestrator(registry=registry, router=RuleBasedRouter(), validator=SkillExecutionValidator())

    from chat_agent.session import ChatSession

    session = ChatSession()
    orchestrator.handle_message("帮学生 5 做 KT 学情分析。", session=session)

    result_event = [event for event in session.events if event.type == "skill_result"][-1]
    assert result_event.data["status"] == "ok"
    assert result_event.data["raw_result"]
    assert result_event.data["report_markdown"] == "报告正文"
    assert "raw_result_preview" not in result_event.data
    assert "report_preview" not in result_event.data


def test_validator_rejects_level_1_execution_without_skill_executor():
    validator = SkillExecutionValidator()

    with pytest.raises(ValidationError):
        validator.validate(
            skill=kt_skill(),
            executor_name=None,
            command=["python", "-c", "print('manual')"],
            output={"llm_analysis": {"report_markdown": "x"}},
        )
