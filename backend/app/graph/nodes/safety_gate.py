"""Safety gate node – routes each turn to PASS, REJECT, or GUIDE."""

from __future__ import annotations

import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage

from app.graph.state import TutorState
from app.services.safety_pipeline import SafetyPipeline

logger = logging.getLogger(__name__)

_pipeline: SafetyPipeline | None = None
_KT_STUDENT_ID_RE = re.compile(r"(?:学生|student)\s*#?\s*(\d+)", re.IGNORECASE)


def _extract_kt_student_id(message: str) -> str | None:
    match = _KT_STUDENT_ID_RE.search(message)
    return match.group(1) if match else None


def _get_pipeline() -> SafetyPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = SafetyPipeline()
    return _pipeline


def _resolve_guide_choice(message: str, pending: dict[str, Any] | None) -> str | None:
    """Resolve a student's input to one exact pending GUIDE option."""
    if not pending:
        return None
    options = [str(item).strip() for item in pending.get("learning_options") or []]
    choice = message.strip()
    selected: str | None = None
    if choice.isdigit():
        index = int(choice) - 1
        if 0 <= index < len(options):
            selected = options[index]
    if selected is None:
        selected = next((item for item in options if choice == item), None)
    return selected


def _resolve_guide_selection(message: str, pending: dict[str, Any] | None) -> str | None:
    """Compatibility helper that renders a selected option as a safe question."""
    selected = _resolve_guide_choice(message, pending)
    safe_query = str((pending or {}).get("safe_query") or "").strip()
    if not safe_query or not selected:
        return None
    return f"{safe_query}\n选定学习方向：{selected}"


def _subject_branch_for_choice(
    selected: str,
    pending: dict[str, Any],
) -> dict[str, Any] | None:
    for item in pending.get("subject_options") or []:
        if isinstance(item, dict) and str(item.get("label") or "").strip() == selected:
            return item
    return None


def _format_focus_guide(
    subject_label: str,
    safe_query: str,
    options: list[str],
    recommended: str,
) -> str:
    numbered = "\n".join(
        f"{index}. {option}{'（推荐）' if option == recommended else ''}"
        for index, option in enumerate(options, 1)
    )
    return (
        f"很好！我们就从“{subject_label}”这个学科视角出发。\n\n"
        f"📘 这一方向的核心探究问题：{safe_query}\n\n"
        f"💡 接下来，你最想先弄清哪一点？\n{numbered}\n\n"
        "直接点击一个选项，也可以回复编号或名称。选好后，我们就从这个知识点开始，一步步学明白。"
    )


async def safety_gate(state: TutorState) -> dict[str, Any]:
    """Run the three-branch safety pipeline on the latest user message."""
    logger.info("[safety_gate] entering – conversation=%s", state.get("conversation_id"))

    from app.services.trace_logger import get_trace_logger
    _trace = get_trace_logger()
    _tid = (state.get("context") or {}).get("_trace_id", "no-trace")
    _trace.debug("[%s] NODE_ENTER safety_gate", _tid)

    messages = state.get("messages", [])
    if not messages:
        logger.info("[safety_gate] no messages – skipping")
        return {
            "safety_branch": "PASS",
            "safety_action": "PASS",
            "context": {**(state.get("context") or {})},
        }

    # Find the latest HumanMessage
    last_user_msg = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_user_msg = msg.content
            break

    if not last_user_msg:
        return {
            "safety_branch": "PASS",
            "safety_action": "PASS",
            "context": {**(state.get("context") or {})},
        }

    # Get student grade from user profile
    profile = state.get("user_profile") or {}
    student_grade = profile.get("grade_level") or profile.get("current_level") or "未知"

    # Build conversation context string
    context_lines = []
    for msg in messages[:-1]:  # exclude current message
        role = "user" if getattr(msg, "type", "") == "human" else "assistant"
        content = getattr(msg, "content", "")
        if content:
            context_lines.append(f"{role}: {content}")
    conversation_context = "\n".join(context_lines[-6:])  # last 6 messages

    ctx = {**(state.get("context") or {})}
    kt_student_id = _extract_kt_student_id(str(last_user_msg))
    if kt_student_id:
        ctx["kt_student_id"] = kt_student_id
    pending_guide = ctx.get("pending_safety_guide")
    if pending_guide and str(pending_guide.get("selection_phase") or "") not in {
        "subject",
        "focus",
    }:
        # Pending GUIDE data created by the old one-round contract must not
        # bypass the new two-round flow. Re-run its original request and open
        # a fresh subject round; the student's current click is intentionally
        # not treated as a final focus choice.
        legacy_query = str(pending_guide.get("original_query") or "").strip()
        if legacy_query:
            last_user_msg = legacy_query
            ctx.pop("pending_safety_guide", None)
            pending_guide = None
    selected_option = _resolve_guide_choice(
        last_user_msg,
        pending_guide,
    )
    if selected_option:
        if str((pending_guide or {}).get("selection_phase") or "") == "subject":
            branch = _subject_branch_for_choice(selected_option, pending_guide)
            if branch:
                focus_options = [
                    str(item).strip()
                    for item in branch.get("learning_options") or []
                    if str(item).strip()
                ]
                recommended = str(branch.get("recommended_option") or "").strip()
                if recommended not in focus_options:
                    recommended = focus_options[0]
                safe_query = str(branch.get("safe_query") or "").strip()
                skill_context = {
                    **((pending_guide.get("guidance_skill") or {})),
                    "status": "ok",
                    "selection_mode": "two_stage",
                    "selection_phase": "focus",
                    "selected_subject_label": selected_option,
                    "school_subject": branch.get("school_subject"),
                    "subject_focus": branch.get("subject_focus"),
                    "safe_query": safe_query,
                    "learning_options": focus_options,
                    "recommended_option": recommended,
                }
                focus_context = {
                    **pending_guide,
                    "branch": "GUIDE",
                    "selection_phase": "focus",
                    "selected_subject_label": selected_option,
                    "school_subject": branch.get("school_subject"),
                    "subject_focus": branch.get("subject_focus"),
                    "safe_query": safe_query,
                    "learning_options": focus_options,
                    "recommended_option": recommended,
                    "guidance_skill": skill_context,
                }
                ctx["pending_safety_guide"] = focus_context
                ctx["safety"] = focus_context
                ctx["safety_context"] = focus_context
                response = _format_focus_guide(
                    selected_option,
                    safe_query,
                    focus_options,
                    recommended,
                )
                return {
                    "safety_branch": "GUIDE",
                    "safety_action": "GUIDE",
                    "safety_context": focus_context,
                    "safety_response": response,
                    "safety_blocked_response": response,
                    "context": ctx,
                    "pre_focus": ["safety_monitor"],
                    "focus_agents": ["safety_monitor"],
                }
        # Architecture invariant: once the student confirms a GUIDE-generated
        # safe option, the safety agent is finished. Mark it PASS and return
        # the transformed request to the complete downstream decision flow.
        resolved_selection = _resolve_guide_selection(last_user_msg, pending_guide)
        ctx.pop("pending_safety_guide", None)
        selection_context = {
            **pending_guide,
            "branch": "PASS",
            "source_branch": "GUIDE",
            "resolved_from_guide": True,
            "selected_option": selected_option,
            "safe_query": str(pending_guide.get("safe_query") or "").strip(),
        }
        ctx["safety"] = selection_context
        ctx["safety_context"] = selection_context
        return {
            "safety_branch": "PASS",
            "safety_action": "PASS",
            "safety_context": selection_context,
            "messages": [HumanMessage(content=resolved_selection)],
            "context": ctx,
            # A confirmed GUIDE focus is already an explicit learning intent.
            # Enter the teaching stage directly with a deterministic queue
            # (stage_executor adopts the whole queue because it contains
            # learning_path); no second LLM routing decision is needed.
            "workflow_type": "adaptive_learning",
            "current_stage": "teaching",
            "stage_counter": 0,
            "next_agents": [
                "cognitive_diagnosis",
                "learning_path",
                "resource_recommender",
                "knowledge_responder",
                "content_polisher",
                "empathy_generator",
            ],
            "pre_focus": ["safety_monitor"],
            "focus_agents": ["safety_monitor"],
        }

    try:
        pipeline = _get_pipeline()
        result = await pipeline.execute(
            query=last_user_msg,
            student_grade=student_grade,
            conversation_context=conversation_context,
        )
    except Exception:
        logger.error("[safety_gate] pipeline failed – using emergency GUIDE", exc_info=True)
        core_topic = SafetyPipeline._infer_core_topic(last_user_msg, "A")
        education_domain, branch_query, branch_options = SafetyPipeline._build_contextual_guide(
            last_user_msg,
            core_topic,
        )
        subject_options = SafetyPipeline._build_fallback_subject_tree(
            last_user_msg,
            core_topic,
            education_domain,
            branch_query,
            branch_options,
        )
        safe_query = f"围绕{core_topic}，你想先从哪个中小学学科视角开始学习？"
        options = [item["label"] for item in subject_options]
        response = SafetyPipeline._format_guide_response(
            safe_query,
            options,
            options[0],
            risk_category="A",
            operational_request=True,
        )
        emergency_context = {
            "branch": "GUIDE",
            "original_query": last_user_msg,
            "core_topic": core_topic,
            "safe_learning_goal": f"了解{core_topic}的原理、风险与防护",
            "risk_category": "A",
            "operational_request": True,
            "pipeline_fallback": True,
            "guidance_skill": {
                "skill_name": "safety-education-guidance",
                "mode": "transform",
                "status": "fallback",
                "selection_mode": "two_stage",
                "safe_query": safe_query,
                "learning_options": options,
                "recommended_option": options[0],
                "subject_options": subject_options,
            },
        }
        fallback_ctx = {**ctx}
        fallback_ctx["safety"] = emergency_context
        fallback_ctx["pending_safety_guide"] = {
            **emergency_context,
            "safe_query": safe_query,
            "learning_options": options,
            "recommended_option": options[0],
            "selection_phase": "subject",
            "subject_options": subject_options,
            "guidance_skill": emergency_context["guidance_skill"],
            "student_grade": student_grade,
            "forbidden_content": [],
        }
        return {
            "safety_branch": "GUIDE",
            "safety_action": "GUIDE",
            "safety_context": emergency_context,
            "safety_response": response,
            "safety_blocked_response": response,
            "pre_focus": ["safety_monitor"],
            "context": fallback_ctx,
        }

    updates: dict[str, Any] = {
        "safety_branch": result.branch,
        "safety_action": result.action,
        "safety_context": result.safety_context,
    }

    # Replace both aliases on every turn. Downstream agents read
    # context.safety_context, so leaving it untouched on PASS leaks the
    # previous turn's GUIDE topic into an unrelated safe request.
    current_safety_context = result.safety_context or {}
    ctx["safety"] = current_safety_context
    ctx["safety_context"] = current_safety_context

    if result.branch == "PASS":
        logger.info("[safety_gate] content is safe")
        ctx.pop("pending_safety_guide", None)
        updates["context"] = ctx

    elif result.branch in ("REJECT", "GUIDE"):
        logger.warning(
            "[safety_gate] short-circuiting: branch=%s",
            result.branch,
        )
        updates["safety_response"] = result.direct_response
        updates["safety_blocked_response"] = result.blocked_response
        if result.branch == "GUIDE":
            skill_result = (result.safety_context or {}).get("guidance_skill") or {}
            subject_options = skill_result.get("subject_options") or []
            ctx["pending_safety_guide"] = {
                "original_query": result.original_query,
                "core_topic": (result.safety_context or {}).get("core_topic"),
                "safe_learning_goal": (result.safety_context or {}).get("safe_learning_goal"),
                "safe_query": result.safe_query,
                "learning_options": result.learning_options or [],
                "recommended_option": result.recommended_option,
                "selection_phase": "subject" if subject_options else "focus",
                "subject_options": subject_options,
                "guidance_skill": skill_result,
                "student_grade": student_grade,
                "risk_category": (result.safety_context or {}).get("risk_category"),
                "operational_request": bool(
                    (result.safety_context or {}).get("operational_request")
                ),
                "forbidden_content": (result.safety_context or {}).get("forbidden_content") or [],
            }
        else:
            ctx.pop("pending_safety_guide", None)
        updates["context"] = ctx
        updates["pre_focus"] = ["safety_monitor"]

    _trace.debug("[%s] NODE_EXIT  safety_gate safety_branch=%s", _tid, result.branch)
    return updates
