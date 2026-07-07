from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SkillPolicy:
    default_entrypoints: list[str] = field(default_factory=list)
    forbidden_actions: list[str] = field(default_factory=list)
    output_paths: list[str] = field(default_factory=list)
    required_inputs: list[str] = field(default_factory=list)
    debug_exceptions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    description: str
    path: Path | None
    instructions: str
    policy: SkillPolicy
    level: int = 2
    executor_name: str | None = None


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    cwd: str | None
    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class SkillExecutionResult:
    skill_name: str
    executor_name: str
    raw_json: dict[str, Any]
    report_markdown: str | None
    predictions: list[dict[str, Any]]
    metrics: dict[str, Any]
    command_results: list[CommandResult]


@dataclass(frozen=True)
class RouterDecision:
    skill_name: str | None
    inputs: dict[str, Any] = field(default_factory=dict)
    missing_inputs: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass(frozen=True)
class OrchestrationResult:
    status: str
    final_response: str
    skill_name: str | None
    raw_result: dict[str, Any] | None
    missing_inputs: list[str] = field(default_factory=list)
    error: str | None = None
