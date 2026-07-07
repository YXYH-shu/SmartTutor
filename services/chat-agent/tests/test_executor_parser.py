import json

import pytest

from chat_agent.executor import CommandExecutor, CommandPolicyError
from chat_agent.result_parser import ResultParser, ResultParserError


def test_executor_rejects_command_outside_allowlist():
    executor = CommandExecutor(allowed_prefixes=[["conda", "run", "-n", "kt"]])

    with pytest.raises(CommandPolicyError):
        executor.run(["python", "-c", "print('bad')"])


def test_executor_captures_successful_command():
    executor = CommandExecutor(allowed_prefixes=[["python", "-c"]])

    result = executor.run(["python", "-c", "print('ok')"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "ok"
    assert result.stderr == ""
    assert result.command == ["python", "-c", "print('ok')"]


def test_result_parser_extracts_report_markdown():
    stdout = json.dumps(
        {
            "status": "ok",
            "predictions": [{"skill_id": 1, "p_correct": 0.8}],
            "metrics": {"count": 1},
            "llm_analysis": {"report_markdown": "## 学情分析\n正文"},
        },
        ensure_ascii=False,
    )

    parsed = ResultParser().parse_kt_stdout(stdout)

    assert parsed.report_markdown == "## 学情分析\n正文"
    assert parsed.raw_json["status"] == "ok"
    assert parsed.predictions == [{"skill_id": 1, "p_correct": 0.8}]


def test_result_parser_rejects_invalid_json():
    with pytest.raises(ResultParserError):
        ResultParser().parse_kt_stdout("not json")
