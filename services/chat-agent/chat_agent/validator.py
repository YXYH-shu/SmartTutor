from __future__ import annotations

from typing import Any

from chat_agent.models import SkillDefinition


class ValidationError(RuntimeError):
    pass


class SkillExecutionValidator:
    def validate(
        self,
        skill: SkillDefinition,
        executor_name: str | None,
        command: list[str] | None,
        output: dict[str, Any] | None,
    ) -> None:
        if skill.level == 1 and not executor_name:
            raise ValidationError(f"Level 1 skill {skill.name} must be executed through the skill executor")

        if command:
            command_text = " ".join(command)
            for forbidden in skill.policy.forbidden_actions:
                if "临时 Python" in forbidden and ("python - <<'PY'" in command_text or command[:2] == ["python", "-c"]):
                    raise ValidationError(f"Execution violates skill policy: {forbidden}")

        if "llm_analysis.report_markdown" in skill.policy.output_paths and output is not None:
            report = output.get("llm_analysis", {}).get("report_markdown")
            if not report:
                raise ValidationError("Required output llm_analysis.report_markdown is missing")
