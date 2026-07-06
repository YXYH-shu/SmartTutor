from __future__ import annotations

import re

from chat_agent.models import SkillPolicy


CODE_SPAN_RE = re.compile(r"`([^`]+)`")
INPUT_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def extract_policy(skill_markdown: str) -> SkillPolicy:
    default_entrypoints: list[str] = []
    forbidden_actions: list[str] = []
    output_paths: list[str] = []
    required_inputs: list[str] = []
    debug_exceptions: list[str] = []
    in_default_required_inputs = False

    for raw_line in skill_markdown.splitlines():
        line = raw_line.strip()
        clean_line = line.lstrip("-*0123456789. ").strip()
        if not clean_line:
            continue

        lower_line = clean_line.lower()
        if line.startswith("##"):
            in_default_required_inputs = False
        elif lower_line == "default student-id mode requires:":
            in_default_required_inputs = True
            continue
        elif lower_line.endswith("requires:") or lower_line.endswith("context:"):
            in_default_required_inputs = False

        if "默认用" in clean_line or "默认执行" in clean_line:
            default_entrypoints.extend(_code_spans(clean_line))

        if clean_line.startswith("不要"):
            forbidden_actions.append(clean_line)

        if "报告读取" in clean_line or "中文报告读取" in clean_line:
            output_paths.extend(_code_spans(clean_line))

        if "调试" in clean_line or "开发" in clean_line:
            debug_exceptions.append(clean_line)

        if in_default_required_inputs:
            input_declaration = clean_line.split(":", 1)[0]
            for input_name in _code_spans(input_declaration):
                if INPUT_NAME_RE.match(input_name):
                    _append_once(required_inputs, input_name)

    return SkillPolicy(
        default_entrypoints=_unique(default_entrypoints),
        forbidden_actions=_unique(forbidden_actions),
        output_paths=_unique(output_paths),
        required_inputs=_unique(required_inputs),
        debug_exceptions=_unique(debug_exceptions),
    )


def _code_spans(text: str) -> list[str]:
    return [match.strip() for match in CODE_SPAN_RE.findall(text) if match.strip()]


def _append_once(items: list[str], item: str) -> None:
    if item not in items:
        items.append(item)


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_items: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            unique_items.append(item)
    return unique_items
