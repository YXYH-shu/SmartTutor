"""Final education-content gate: PASS, PATCH, or REGENERATE."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.graph.state import TutorState
from app.services.agents import get_agent

logger = logging.getLogger(__name__)

_CHECK_NAMES = (
    "scientific_reliability",
    "educational_completeness",
    "structural_clarity",
    "content_safety",
)
_VALID_ACTIONS = {"PASS", "PATCH", "REGENERATE"}
_LIST_PATTERN = re.compile(r"^\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)、]\s*)")


def _checks_pass(output: dict[str, Any]) -> bool:
    checks = output.get("checks")
    return isinstance(checks, dict) and all(checks.get(name) is True for name in _CHECK_NAMES)


def _latest_user_message(state: TutorState) -> str:
    for message in reversed(state.get("messages", [])):
        if getattr(message, "type", "") == "human":
            content = getattr(message, "content", "")
            return content if isinstance(content, str) else ""
    return ""


def _structure_count(text: str) -> int:
    return sum(1 for line in text.splitlines() if _LIST_PATTERN.match(line))


def _local_patch_is_safe(original: str, patched: str) -> bool:
    """Reject a supposed local patch that behaves like a full rewrite."""
    if not patched.strip():
        return False
    original_length = max(len(original), 1)
    length_ratio = len(patched) / original_length
    if not 0.75 <= length_ratio <= 1.35:
        return False
    return _structure_count(patched) >= _structure_count(original)


def _compact_safety_constraints(value: Any) -> dict[str, Any]:
    """Keep only correction-relevant safety facts out of the full trace tree."""
    if not isinstance(value, dict):
        return {}
    compact = {
        key: value[key]
        for key in (
            "branch",
            "risk_category",
            "core_topic",
            "safe_learning_goal",
            "operational_request",
            "forbidden_content",
            "allowed_content",
            "safe_query",
            "selected_option",
        )
        if key in value
    }
    guidance = value.get("guidance_skill")
    if isinstance(guidance, dict):
        compact["guidance"] = {
            key: guidance[key]
            for key in (
                "education_domain",
                "safe_query",
                "constraints_applied",
                "preserved_elements",
            )
            if key in guidance
        }
    return compact


async def content_correction(state: TutorState) -> dict[str, Any]:
    """Audit a completed response without taking over content generation."""
    original = state.get("final_response")
    if not isinstance(original, str) or not original:
        return {}

    ctx = {**(state.get("context") or {})}
    regeneration_count = int(ctx.get("_content_regeneration_count") or 0)
    safety_constraints = _compact_safety_constraints(
        ctx.get("safety_context") or state.get("safety_context") or {}
    )

    try:
        agent = get_agent("content_corrector")
        result = await agent.execute(
            input_data={
                "original_response": original,
                "student_question": _latest_user_message(state),
                "subject": ctx.get("subject", ""),
                "grade_level": (state.get("user_profile") or {}).get("current_level", ""),
                "conversation_stage": state.get("current_stage", ""),
                "safety_constraints": safety_constraints,
            },
            context={
                "conversation_id": state.get("conversation_id", ""),
                "user_id": state.get("user_id", ""),
                "turn_id": ctx.get("turn_id"),
            },
        )
        output = result.get("output")
        if not isinstance(output, dict):
            raise ValueError("content_corrector returned a non-object output")
    except Exception as exc:
        logger.warning("[content_correction] audit failed; passing original: %s", exc)
        output = {
            "action": "PASS",
            "issues": [f"验收服务异常：{type(exc).__name__}"],
            "patched_response": "",
            "checks": {},
        }
        status = "audit_fallback"
    else:
        status = "audited"

    requested_action = str(output.get("action", "PASS")).upper()
    if requested_action not in _VALID_ACTIONS:
        requested_action = "PASS"

    issues = [
        item.strip()
        for item in output.get("issues", [])
        if isinstance(item, str) and item.strip()
    ]
    action = requested_action
    final = original

    if action == "PASS":
        # PASS is always byte-for-byte; any model-provided alternative is ignored.
        status = "passed" if status == "audited" else status
    elif action == "PATCH":
        patched = output.get("patched_response")
        if (
            _checks_pass(output)
            and isinstance(patched, str)
            and _local_patch_is_safe(original, patched)
        ):
            final = patched
            status = "patched"
        else:
            action = "REGENERATE"
            status = "patch_rejected"
            issues.append("局部修改超出允许范围或未通过四项验收，需要由原内容生成智能体重写。")

    if action == "REGENERATE" and regeneration_count >= 1:
        # A single upstream rewrite is allowed. Never create an unbounded loop.
        action = "PASS"
        status = "regeneration_limit"
        issues.append("已达到单次重写上限，保留最近一次生成结果。")

    trace_output = {
        "action": action,
        "requested_action": requested_action,
        "issues": issues,
        "patched_response": final if status == "patched" else "",
        "checks": output.get("checks", {}),
        "status": status,
        "structure_preserved": (
            _structure_count(final) >= _structure_count(original)
        ),
        "regeneration_count": regeneration_count,
    }
    ctx["content_corrector"] = trace_output
    ctx["_last_agent"] = "content_corrector"
    ctx["_last_output"] = trace_output

    logger.info(
        "[content_correction] action=%s requested=%s status=%s",
        action,
        requested_action,
        status,
    )
    return {"final_response": final, "context": ctx}
