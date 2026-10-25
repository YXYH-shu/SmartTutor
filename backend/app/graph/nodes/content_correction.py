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


# ---------------------------------------------------------------------------
# V2.5 展示字段（scores / severity / issue_details / patches / summary / change_ratio）
# 只用于前端展示，不参与 PASS/PATCH/REGENERATE 判定，也不被其他智能体读取。
# 所有归一化都必须容错：模型漏填或格式不对时返回默认值，绝不抛异常。
# ---------------------------------------------------------------------------
_SCORE_KEYS = (
    "scientific_argumentation",
    "metacognitive_guidance",
    "scientific_discourse",
    "content_safety",
)
_VALID_SEVERITY = {"none", "minor", "major"}


def _normalize_scores(value: Any) -> dict[str, int | None]:
    scores: dict[str, int | None] = {}
    source = value if isinstance(value, dict) else {}
    for key in _SCORE_KEYS:
        raw = source.get(key)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            scores[key] = None
        else:
            scores[key] = max(0, min(100, int(round(raw))))
    return scores


def _normalize_issue_details(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    details: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        problem = str(item.get("problem") or "").strip()
        if not problem:
            continue
        details.append(
            {
                "dimension": str(item.get("dimension") or "").strip(),
                "problem": problem,
                "reason": str(item.get("reason") or "").strip(),
            }
        )
    return details


def _normalize_dimension_notes(value: Any) -> dict[str, str]:
    source = value if isinstance(value, dict) else {}
    notes: dict[str, str] = {}
    for key in _SCORE_KEYS:
        raw = source.get(key)
        notes[key] = raw.strip() if isinstance(raw, str) else ""
    return notes


def _squash(text: str) -> str:
    """Drop whitespace and markdown emphasis so quote matching tolerates formatting."""
    return re.sub(r"[\s*_`#>]+", "", text)


def _normalize_dimension_evidence(value: Any, original: str) -> dict[str, str]:
    """Keep a quote only if it really appears in the original answer."""
    source = value if isinstance(value, dict) else {}
    haystack = _squash(original)
    evidence: dict[str, str] = {}
    for key in _SCORE_KEYS:
        raw = source.get(key)
        quote = raw.strip() if isinstance(raw, str) else ""
        evidence[key] = quote if quote and len(quote) <= 80 and _squash(quote) in haystack else ""
    return evidence


def _derive_patches(original: str, patched: str, reason: str) -> list[dict[str, str]]:
    """Fallback: derive before/after pairs by diffing lines when the model gave none."""
    import difflib

    before_lines = original.splitlines()
    after_lines = patched.splitlines()
    matcher = difflib.SequenceMatcher(None, before_lines, after_lines, autojunk=False)
    derived: list[dict[str, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "replace":
            continue
        before = "\n".join(before_lines[i1:i2]).strip()
        after = "\n".join(after_lines[j1:j2]).strip()
        if before and after:
            derived.append({"before": before, "after": after, "reason": reason})
    return derived


def _normalize_patches(
    value: Any, original: str, patched: str, fallback_reason: str
) -> list[dict[str, str]]:
    """Keep only patches whose ``before`` really exists in the original text."""
    patches: list[dict[str, str]] = []
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            before = str(item.get("before") or "").strip()
            after = str(item.get("after") or "").strip()
            if before and after and before in original and before != after:
                patches.append(
                    {
                        "before": before,
                        "after": after,
                        "reason": str(item.get("reason") or "").strip() or fallback_reason,
                    }
                )
    if not patches and patched:
        patches = _derive_patches(original, patched, fallback_reason)
    return patches


def _change_ratio(original: str, final: str) -> float:
    if original == final or not original:
        return 0.0
    import difflib

    ratio = 1.0 - difflib.SequenceMatcher(None, original, final, autojunk=False).ratio()
    return round(max(0.0, min(1.0, ratio)), 3)


def _build_display_fields(
    output: dict[str, Any], *, original: str, final: str, patched: bool
) -> dict[str, Any]:
    """Build the V2.5 display-only fields. Never raises."""
    try:
        issue_details = _normalize_issue_details(output.get("issue_details"))
        severity = output.get("severity")
        severity = severity if severity in _VALID_SEVERITY else None
        summary = output.get("summary")
        fallback_reason = issue_details[0]["reason"] if issue_details else ""
        return {
            "scores": _normalize_scores(output.get("scores")),
            "severity": severity,
            "issue_details": issue_details,
            "patches": (
                _normalize_patches(output.get("patches"), original, final, fallback_reason)
                if patched
                else []
            ),
            "summary": summary.strip() if isinstance(summary, str) else "",
            "change_ratio": _change_ratio(original, final) if patched else 0.0,
            "dimension_notes": _normalize_dimension_notes(output.get("dimension_notes")),
            # 引用只和“被验收的原回答”比对，PATCH 后也以原回答为准
            "dimension_evidence": _normalize_dimension_evidence(
                output.get("dimension_evidence"), original
            ),
        }
    except Exception:  # noqa: BLE001 - display fields must never break the gate
        logger.warning("[content_correction] failed to build display fields", exc_info=True)
        return {
            "scores": _normalize_scores(None),
            "severity": None,
            "issue_details": [],
            "patches": [],
            "summary": "",
            "change_ratio": 0.0,
            "dimension_notes": _normalize_dimension_notes(None),
            "dimension_evidence": _normalize_dimension_evidence(None, ""),
        }


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
        # V2.5 展示字段：只增不改，上面的 V2.0 字段含义保持不变
        **_build_display_fields(
            output, original=original, final=final, patched=(status == "patched")
        ),
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
