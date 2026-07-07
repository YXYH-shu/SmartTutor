import json
from pathlib import Path

import pytest

from chat_agent.executor import CommandResult
from chat_agent.models import SkillDefinition, SkillPolicy
from chat_agent.session import ChatSession
from chat_agent.skill_markdown_executor import MissingSkillInputs, SkillMarkdownExecutor


class FakeExecutor:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run(self, command, cwd=None, timeout=None):
        self.calls.append({"command": list(command), "cwd": cwd, "timeout": timeout})
        return self.result


def command_result(stdout, exit_code=0, stderr=""):
    return CommandResult(command=["fake"], cwd=None, exit_code=exit_code, stdout=stdout, stderr=stderr)


def kt_stdout():
    return json.dumps(
        {
            "status": "ok",
            "llm_analysis": {"report_markdown": "报告正文"},
            "predictions": [],
            "metrics": {"num_predictions": 348},
        },
        ensure_ascii=False,
    )


def skill(tmp_path: Path):
    return SkillDefinition(
        name="kt-runtime-skill",
        description="Use when 需要基于学生 ID 运行 KT 预测。",
        path=tmp_path,
        instructions="完整 SKILL.md 内容",
        policy=SkillPolicy(
            default_entrypoints=["conda run -n kt python scripts/run_kt.py"],
            required_inputs=["student_id"],
            output_paths=["llm_analysis.report_markdown"],
        ),
        level=1,
        executor_name="skill_markdown",
    )


def skill_without_entrypoint(tmp_path: Path):
    return SkillDefinition(
        name="kt-runtime-skill",
        description="Use when 需要基于学生 ID 运行 KT 预测。",
        path=tmp_path,
        instructions="完整 SKILL.md 内容",
        policy=SkillPolicy(
            default_entrypoints=[],
            required_inputs=["student_id"],
            output_paths=["llm_analysis.report_markdown"],
        ),
        level=1,
        executor_name="skill_markdown",
    )


def test_skill_markdown_executor_runs_declared_entrypoint_and_records_events(tmp_path):
    executor = FakeExecutor(command_result(kt_stdout()))
    session = ChatSession()
    runner = SkillMarkdownExecutor(executor=executor)

    result = runner.run(
        skill(tmp_path),
        {"student_id": "5", "history_context": "学生最近在学电路。"},
        session=session,
    )

    assert result.report_markdown == "报告正文"
    assert executor.calls == [
        {
            "command": [
                "conda",
                "run",
                "-n",
                "kt",
                "python",
                "scripts/run_kt.py",
                "--student-id",
                "5",
                "--history-context",
                "学生最近在学电路。",
            ],
            "cwd": tmp_path,
            "timeout": 120,
        }
    ]
    event_types = [event.type for event in session.events]
    assert event_types == [
        "skill_loaded",
        "skill_policy_extracted",
        "command_prepared",
        "command_started",
        "command_finished",
    ]
    prepared = session.events[2]
    assert prepared.data["command"] == "conda run -n kt python scripts/run_kt.py --student-id 5 --history-context '学生最近在学电路。'"
    assert prepared.data["cwd"] == str(tmp_path)
    finished = session.events[4]
    assert "stdout" in finished.data
    assert "stderr" in finished.data
    assert "stdout_preview" not in finished.data
    assert "stderr_preview" not in finished.data


def test_skill_markdown_executor_reports_missing_inputs(tmp_path):
    runner = SkillMarkdownExecutor(executor=FakeExecutor(command_result(kt_stdout())))

    with pytest.raises(MissingSkillInputs) as exc_info:
        runner.run(skill(tmp_path), {"history_context": "学生最近在学电路。"})

    assert exc_info.value.missing_inputs == ["student_id"]


def test_skill_markdown_executor_runs_with_student_id_only_by_default(tmp_path):
    executor = FakeExecutor(command_result(kt_stdout()))
    runner = SkillMarkdownExecutor(executor=executor)

    runner.run(skill(tmp_path), {"student_id": "5"})

    assert executor.calls[0]["command"] == [
        "conda",
        "run",
        "-n",
        "kt",
        "python",
        "scripts/run_kt.py",
        "--student-id",
        "5",
    ]


def test_skill_markdown_executor_maps_historical_questions_to_history_context(tmp_path):
    executor = FakeExecutor(command_result(kt_stdout()))
    runner = SkillMarkdownExecutor(executor=executor)

    runner.run(
        skill(tmp_path),
        {
            "student_id": "42",
            "historical_questions": [
                "最近在学电路，想知道为什么闭合回路才能让小灯泡亮起来。",
                "如果导线断开，为什么电流就不能继续流动？",
            ],
            "unexpected_field": "不要透传给 CLI",
        },
    )

    assert executor.calls[0]["command"] == [
        "conda",
        "run",
        "-n",
        "kt",
        "python",
        "scripts/run_kt.py",
        "--student-id",
        "42",
        "--history-context",
        "最近在学电路，想知道为什么闭合回路才能让小灯泡亮起来。\n如果导线断开，为什么电流就不能继续流动？",
    ]


def test_skill_markdown_executor_uses_kt_default_entrypoint_when_policy_is_stale(tmp_path):
    executor = FakeExecutor(command_result(kt_stdout()))
    runner = SkillMarkdownExecutor(executor=executor)

    runner.run(skill_without_entrypoint(tmp_path), {"student_id": "5"})

    assert executor.calls[0]["command"] == [
        "conda",
        "run",
        "-n",
        "kt",
        "python",
        "scripts/run_kt.py",
        "--student-id",
        "5",
    ]
