from __future__ import annotations

import re
from pathlib import Path

from chat_agent.models import SkillDefinition
from chat_agent.policy import extract_policy


FRONTMATTER_RE = re.compile(r"\A---\s*\n(?P<body>.*?)\n---\s*\n", re.DOTALL)


class SkillLoader:
    def __init__(self, skill_paths: list[str | Path]):
        self.skill_paths = [Path(path) for path in skill_paths]

    def load(self) -> list[SkillDefinition]:
        skills: list[SkillDefinition] = []
        for path in self.skill_paths:
            skill_md = path / "SKILL.md"
            if not skill_md.exists():
                continue
            text = skill_md.read_text(encoding="utf-8")
            metadata = _parse_frontmatter(text)
            name = metadata.get("name") or path.name
            description = metadata.get("description", "")
            skills.append(
                SkillDefinition(
                    name=name,
                    description=description,
                    path=path,
                    instructions=text,
                    policy=extract_policy(text),
                    level=1 if name == "kt-runtime-skill" else 2,
                    executor_name="skill_markdown" if name == "kt-runtime-skill" else None,
                )
            )
        return skills


def _parse_frontmatter(text: str) -> dict[str, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}
    metadata: dict[str, str] = {}
    for line in match.group("body").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")
    return metadata
