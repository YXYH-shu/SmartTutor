from chat_agent.models import SkillExecutionResult, SkillDefinition, SkillPolicy
from chat_agent.orchestrator import Orchestrator
from chat_agent.router import RuleBasedRouter
from chat_agent.session import ChatSession
from chat_agent.skill_registry import SkillRegistry
from chat_agent.validator import SkillExecutionValidator


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


def make_orchestrator(skill_executor):
    registry = SkillRegistry(skill_executor=skill_executor)
    registry.register(
        SkillDefinition(
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
        ),
    )
    return Orchestrator(registry=registry, router=RuleBasedRouter(), validator=SkillExecutionValidator())


def test_session_runs_kt_with_student_id_only():
    skill_executor = FakeSkillExecutor()
    orchestrator = make_orchestrator(skill_executor)
    session = ChatSession()

    result = orchestrator.handle_message("帮学生 5 做 KT 学情分析", session=session)

    assert result.status == "ok"
    assert result.final_response == "报告正文"
    assert session.pending_skill is None
    assert session.pending_inputs == []
    assert session.slots["student_id"] == "5"
    assert skill_executor.inputs == {"student_id": "5"}


def test_session_records_messages_and_workflow_events():
    skill_executor = FakeSkillExecutor()
    orchestrator = make_orchestrator(skill_executor)
    session = ChatSession()

    orchestrator.handle_message("帮学生 5 做 KT 学情分析", session=session)

    assert [message.role for message in session.messages] == ["user", "assistant"]
    event_types = [event.type for event in session.events]
    assert "message_received" in event_types
    assert "skill_selected" in event_types
    assert "slot_missing" not in event_types
    assert "skill_execution_started" in event_types
    assert "skill_execution_finished" in event_types
    assert "validation_passed" in event_types
    assert event_types[-1] == "workflow_finished"


def test_kt_request_without_student_id_asks_for_student_id_only():
    skill_executor = FakeSkillExecutor()
    orchestrator = make_orchestrator(skill_executor)
    session = ChatSession()

    result = orchestrator.handle_message("做 KT 学情分析", session=session)

    assert result.status == "need_input"
    assert result.missing_inputs == ["student_id"]
    assert result.final_response == "请补充学生 ID。"
    assert session.pending_skill == "kt-runtime-skill"
    assert session.pending_inputs == ["student_id"]
    assert skill_executor.inputs is None


def test_pending_kt_can_be_cancelled():
    orchestrator = make_orchestrator(FakeSkillExecutor())
    session = ChatSession()

    orchestrator.handle_message("做 KT 学情分析", session=session)
    result = orchestrator.handle_message("取消", session=session)

    assert result.status == "cancelled"
    assert result.skill_name is None
    assert result.final_response == "已取消当前 KT 分析请求。"
    assert session.pending_skill is None
    assert session.pending_inputs == []
