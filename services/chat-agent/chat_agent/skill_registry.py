from __future__ import annotations

from typing import Any

from chat_agent.models import SkillDefinition, SkillExecutionResult


class SkillNotFoundError(KeyError):
    pass


class SkillExecutorNotConfiguredError(RuntimeError):
    pass


class SkillRegistry:
    def __init__(self, skill_executor: Any | None = None):
        self._skills: dict[str, SkillDefinition] = {}
        self.skill_executor = skill_executor

    def register(self, skill: SkillDefinition) -> None:
        self._skills[skill.name] = skill

    def list_skills(self) -> list[SkillDefinition]:
        return list(self._skills.values())

    def get_skill(self, name: str) -> SkillDefinition:
        try:
            return self._skills[name]
        except KeyError as exc:
            raise SkillNotFoundError(name) from exc

    def find_candidates(self, message: str) -> list[SkillDefinition]:
        lowered = message.lower()
        candidates: list[SkillDefinition] = []
        for skill in self._skills.values():
            haystack = f"{skill.name} {skill.description} {skill.instructions}".lower()
            if any(token in lowered for token in ["kt", "学情", "掌握", "知识点", "预测"]):
                if "kt" in haystack or "学情" in haystack:
                    candidates.append(skill)
        return candidates

    def run_skill(self, name: str, inputs: dict[str, Any], session=None) -> SkillExecutionResult:
        if self.skill_executor is None:
            raise SkillExecutorNotConfiguredError("Skill executor is not configured")
        return self.skill_executor.run(self.get_skill(name), inputs, session=session)
