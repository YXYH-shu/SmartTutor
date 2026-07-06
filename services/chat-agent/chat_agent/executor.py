from __future__ import annotations

import subprocess
from pathlib import Path

from chat_agent.models import CommandResult


class CommandPolicyError(RuntimeError):
    pass


class CommandExecutionError(RuntimeError):
    pass


class CommandExecutor:
    def __init__(self, allowed_prefixes: list[list[str]], default_timeout: int = 120):
        self.allowed_prefixes = allowed_prefixes
        self.default_timeout = default_timeout

    def run(
        self,
        command: list[str],
        cwd: str | Path | None = None,
        timeout: int | None = None,
    ) -> CommandResult:
        if not self._is_allowed(command):
            raise CommandPolicyError(f"Command is outside allowlist: {' '.join(command)}")

        process = subprocess.run(
            command,
            cwd=str(cwd) if cwd is not None else None,
            text=True,
            capture_output=True,
            timeout=timeout or self.default_timeout,
            check=False,
        )
        return CommandResult(
            command=list(command),
            cwd=str(cwd) if cwd is not None else None,
            exit_code=process.returncode,
            stdout=process.stdout,
            stderr=process.stderr,
        )

    def _is_allowed(self, command: list[str]) -> bool:
        return any(command[: len(prefix)] == prefix for prefix in self.allowed_prefixes)
