from __future__ import annotations

from pathlib import Path
import shlex
from typing import Any

from chat_agent.executor import CommandExecutionError
from chat_agent.models import SkillDefinition, SkillExecutionResult
from chat_agent.result_parser import ResultParser
from chat_agent.session import ChatSession


KT_RUNTIME_DEFAULT_ENTRYPOINT = "conda run -n kt python scripts/run_kt.py"
KT_RUNTIME_CLI_INPUTS = {
    "config_file",
    "request_file",
    "request_json",
    "student_id",
    "trace_pairs",
    "trace_json",
    "trace_file",
    "targets",
    "history_limit",
    "request_id",
    "device",
    "initial_query",
    "history_context",
}


class MissingSkillInputs(ValueError):
    def __init__(self, missing_inputs: list[str]):
        self.missing_inputs = missing_inputs
        super().__init__(f"Missing required skill inputs: {', '.join(missing_inputs)}")


class SkillMarkdownExecutor:
    name = "skill_markdown"

    def __init__(self, executor, timeout: int = 120):
        self.executor = executor
        self.timeout = timeout
        self.parser = ResultParser()

    def run(
        self,
        skill: SkillDefinition,
        inputs: dict[str, Any],
        *,
        session: ChatSession | None = None,
    ) -> SkillExecutionResult:
        normalized_inputs = _normalized_inputs(inputs)
        missing = _missing_inputs(skill, normalized_inputs)
        if missing:
            raise MissingSkillInputs(missing)

        cwd = Path(skill.path) if skill.path is not None else None
        command = _command_from_skill(skill, normalized_inputs)
        command_text = shlex.join(command)

        _event(
            session,
            "skill_loaded",
            f"读取 skill：{skill.name}",
            skill_name=skill.name,
            path=str(skill.path) if skill.path is not None else None,
        )
        _event(
            session,
            "skill_policy_extracted",
            "已从 SKILL.md 提取执行策略。",
            skill_name=skill.name,
            default_entrypoints=list(skill.policy.default_entrypoints),
            required_inputs=list(skill.policy.required_inputs),
            output_paths=list(skill.policy.output_paths),
        )
        _event(
            session,
            "command_prepared",
            "已根据 SKILL.md 准备执行命令。",
            skill_name=skill.name,
            command=command_text,
            cwd=str(cwd) if cwd is not None else None,
        )
        _event(
            session,
            "command_started",
            "开始执行 skill 命令。",
            skill_name=skill.name,
            command=command_text,
            cwd=str(cwd) if cwd is not None else None,
        )
        command_result = self.executor.run(command, cwd=cwd, timeout=self.timeout)
        _event(
            session,
            "command_finished",
            "skill 命令执行完成。",
            skill_name=skill.name,
            command=command_text,
            cwd=str(cwd) if cwd is not None else None,
            exit_code=command_result.exit_code,
            stdout=command_result.stdout,
            stderr=command_result.stderr,
        )

        if command_result.exit_code != 0:
            raise CommandExecutionError(command_result.stderr or command_result.stdout)

        parsed = self.parser.parse_kt_stdout(command_result.stdout)
        return SkillExecutionResult(
            skill_name=skill.name,
            executor_name=self.name,
            raw_json=parsed.raw_json,
            report_markdown=parsed.report_markdown,
            predictions=parsed.predictions,
            metrics=parsed.metrics,
            command_results=[command_result],
        )


def _normalized_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    normalized = {str(key): value for key, value in inputs.items() if value not in (None, "")}
    historical_questions = normalized.pop("historical_questions", None)
    if historical_questions:
        questions_context = _stringify_history_context(historical_questions)
        existing_context = str(normalized.get("history_context", "")).strip()
        if existing_context and questions_context:
            normalized["history_context"] = f"{existing_context}\n{questions_context}"
        elif questions_context:
            normalized["history_context"] = questions_context
    return normalized


def _missing_inputs(skill: SkillDefinition, inputs: dict[str, Any]) -> list[str]:
    return [name for name in skill.policy.required_inputs if not inputs.get(name)]


def _command_from_skill(skill: SkillDefinition, inputs: dict[str, Any]) -> list[str]:
    default_entrypoints = list(skill.policy.default_entrypoints)
    if not default_entrypoints and skill.name == "kt-runtime-skill":
        default_entrypoints = [KT_RUNTIME_DEFAULT_ENTRYPOINT]
    if not default_entrypoints:
        raise CommandExecutionError(f"Skill {skill.name} does not declare a default entrypoint.")

    command = shlex.split(default_entrypoints[0])
    ordered_input_names = list(skill.policy.required_inputs)
    extra_input_names = sorted(name for name in inputs if name not in set(ordered_input_names))
    for name in ordered_input_names + extra_input_names:
        if skill.name == "kt-runtime-skill" and name not in KT_RUNTIME_CLI_INPUTS:
            continue
        value = inputs.get(name)
        if value in (None, ""):
            continue
        if name == "targets" and str(value).strip() == "all":
            continue
        command.extend([f"--{name.replace('_', '-')}", str(value)])
    return command


def _stringify_history_context(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def _event(session: ChatSession | None, event_type: str, message: str, **data: Any) -> None:
    if session is not None:
        session.add_event(event_type, message, **data)
