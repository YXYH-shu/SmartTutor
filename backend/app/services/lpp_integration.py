"""Adapter between SmartTutor's learning-path Agent and the local LPP Runtime."""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import re
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LppRuntimeOutput:
    data: dict[str, Any]
    raw_json: str


def extract_explicit_target_question(input_data: dict[str, Any]) -> int | None:
    direct = input_data.get("target_question_id")
    if direct not in (None, ""):
        try:
            return int(direct)
        except (TypeError, ValueError):
            return None

    message = str(input_data.get("current_message") or input_data.get("goal") or "")
    patterns = (
        r"(?:目标题(?:号)?|目标题目(?:编号)?|target\s*question(?:\s*id)?)"
        r"\s*(?:是|为|[:：#])?\s*(\d+)",
        r"(?:题号|题目编号)\s*(?:是|为|[:：#])?\s*(\d+)",
    )
    for pattern in patterns:
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _coerce_skill_id(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = str(value or "").strip()
    if text.isdigit():
        return int(text)
    match = re.fullmatch(r"KP0*(\d+)", text, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def normalize_skill_priorities(priorities: list[Any]) -> list[int]:
    ranked: list[tuple[float, int]] = []
    for item in priorities:
        if not isinstance(item, dict):
            continue
        skill_id = _coerce_skill_id(item.get("skill_id"))
        if skill_id is None:
            continue
        try:
            mastery = float(item.get("mastery_rate", 1.0))
        except (TypeError, ValueError):
            mastery = 1.0
        ranked.append((mastery, skill_id))
    ranked.sort(key=lambda item: item[0])
    return list(dict.fromkeys(skill_id for _, skill_id in ranked))


def skill_priorities_from_diagnosis(diagnosis: dict[str, Any]) -> list[int]:
    states = diagnosis.get("knowledge_states") or []
    if isinstance(states, list):
        priorities = normalize_skill_priorities(states)
        if priorities:
            return priorities

    rates = diagnosis.get("mastery_rates") or {}
    if isinstance(rates, dict):
        return normalize_skill_priorities(
            [
                {"skill_id": skill_id, "mastery_rate": mastery}
                for skill_id, mastery in rates.items()
            ]
        )
    return []


_DIAGNOSIS_PROMPT_STATE_FIELDS = (
    "skill_id",
    "skill_name",
    "type",
    "mastery_percent",
    "mastery_rate",
    "mastery_label",
    "status",
    "evidence",
)

_LPP_PROMPT_QUESTION_FIELDS = (
    "question_id",
    "question_text",
    "question_type",
    "question_type_code",
    "difficulty",
    "grade",
    "options",
    "order",
)

_LPP_PROMPT_KNOWLEDGE_FIELDS = (
    "knowledge_point_id",
    "knowledge_point_name",
    "skill_id",
    "skill_name",
)


def _diagnosis_mastery_rate(state: dict[str, Any]) -> float:
    raw_rate = state.get("mastery_rate")
    try:
        if raw_rate is not None:
            return float(raw_rate)
        raw_percent = str(state.get("mastery_percent") or "").strip().removesuffix("%")
        return float(raw_percent) / 100.0
    except (TypeError, ValueError):
        return 1.0


def build_diagnosis_prompt_context(
    diagnosis: dict[str, Any],
    max_states: int = 10,
) -> dict[str, Any]:
    """Project complete diagnosis facts to the subset needed for path explanation."""
    states = [
        state
        for state in (diagnosis.get("knowledge_states") or [])
        if isinstance(state, dict)
    ]
    states.sort(key=_diagnosis_mastery_rate)

    selected: list[dict[str, Any]] = []
    seen_skill_ids: set[str] = set()
    for state in states:
        skill_id = str(state.get("skill_id") or state.get("skill_name") or "")
        if not skill_id or skill_id in seen_skill_ids:
            continue
        seen_skill_ids.add(skill_id)
        selected.append(
            {
                field: state[field]
                for field in _DIAGNOSIS_PROMPT_STATE_FIELDS
                if field in state
            }
        )
        if len(selected) >= max_states:
            break

    return {
        "diagnosis_summary": diagnosis.get("diagnosis_summary", ""),
        "recommended_actions": list(diagnosis.get("recommended_actions") or []),
        "diagnosis_source": diagnosis.get("diagnosis_source"),
        "total_count": len(states),
        "weak_count": sum(state.get("status") == "weak" for state in states),
        "developing_count": sum(
            state.get("status") == "developing" for state in states
        ),
        "mastered_count": sum(state.get("status") == "mastered" for state in states),
        "priority_states": selected,
    }


def build_learning_profile_prompt_context(profile: dict[str, Any]) -> dict[str, Any]:
    """Keep only learner attributes needed to explain the fixed LPP path."""
    return {
        field: profile[field]
        for field in ("current_level", "learning_style", "grade_level")
        if profile.get(field) not in (None, "")
    }


def _prompt_knowledge_points(raw_points: Any) -> list[dict[str, Any]]:
    return [
        {
            field: point[field]
            for field in _LPP_PROMPT_KNOWLEDGE_FIELDS
            if field in point
        }
        for point in (raw_points or [])
        if isinstance(point, dict)
    ]


def _prompt_question(question: dict[str, Any]) -> dict[str, Any]:
    projected = {
        field: copy.deepcopy(question[field])
        for field in _LPP_PROMPT_QUESTION_FIELDS
        if field in question
    }
    projected["knowledge_points"] = _prompt_knowledge_points(
        question.get("knowledge_points")
    )
    return projected


def build_lpp_prompt_context(result: dict[str, Any]) -> dict[str, Any]:
    """Project complete LPP output to immutable P1-P5 facts and explanations."""
    target = result.get("target") or {}
    projected_target = _prompt_question(target) if isinstance(target, dict) else {}
    for field in (
        "baseline_correctness_probability",
        "planned_correctness_probability",
        "correctness_probability_gain",
    ):
        if isinstance(target, dict) and field in target:
            projected_target[field] = target[field]

    questions = [
        _prompt_question(question)
        for question in ((result.get("recommendation") or {}).get("questions") or [])
        if isinstance(question, dict)
    ]
    plan_items = [
        {
            field: item[field]
            for field in ("priority", "question_id", "purpose_and_effect")
            if field in item
        }
        for item in (result.get("plan_items") or [])
        if isinstance(item, dict)
    ]
    return {
        "student_id": str(result.get("student_id") or ""),
        "target": projected_target,
        "recommendation": {"count": len(questions), "questions": questions},
        "plan_items": plan_items,
    }


def lpp_prompt_skill_ids(result: dict[str, Any]) -> set[str]:
    """Return skill identifiers referenced by the fixed P1-P5 questions."""
    skill_ids: set[str] = set()
    questions = (result.get("recommendation") or {}).get("questions") or []
    for question in questions:
        if not isinstance(question, dict):
            continue
        for point in question.get("knowledge_points") or []:
            if not isinstance(point, dict):
                continue
            value = point.get("knowledge_point_id") or point.get("skill_id")
            if value not in (None, ""):
                skill_ids.add(_prompt_skill_key(value))
    return skill_ids


def _prompt_skill_key(value: Any) -> str:
    text = str(value or "").strip()
    match = re.fullmatch(r"KP0*(\d+)", text, flags=re.IGNORECASE)
    if match:
        return str(int(match.group(1)))
    return str(int(text)) if text.isdigit() else text


def build_relevant_knowledge_graph_prompt_context(
    graph: dict[str, Any],
    skill_ids: set[str],
) -> dict[str, Any]:
    """Keep only graph nodes used by P1-P5 and edges internal to that subset."""
    nodes = []
    retained_ids: set[str] = set()
    for node in graph.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        raw_id = node.get("id") or node.get("skill_id")
        node_id = _prompt_skill_key(raw_id)
        if node_id and node_id in skill_ids:
            nodes.append(copy.deepcopy(node))
            retained_ids.add(node_id)

    edges = []
    for edge in graph.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        source = _prompt_skill_key(edge.get("source"))
        target = _prompt_skill_key(edge.get("target"))
        if source in retained_ids and target in retained_ids:
            edges.append(copy.deepcopy(edge))
    return {"nodes": nodes, "edges": edges}


def validate_lpp_result(result: dict[str, Any]) -> None:
    if result.get("status") != "ok":
        raise ValueError(f"LPP runtime status is not ok: {result.get('message')}")
    if result.get("message") != "recommendations_ready":
        raise ValueError(f"LPP runtime is not ready: {result.get('message')}")

    recommendation = result.get("recommendation") or {}
    questions = recommendation.get("questions") or []
    if len(questions) != 5:
        raise ValueError("LPP recommendation must contain exactly 5 questions")
    if [question.get("order") for question in questions] != [1, 2, 3, 4, 5]:
        raise ValueError("LPP question orders must be consecutive from 1 to 5")
    for question in questions:
        if not question.get("question_text"):
            raise ValueError("LPP question is missing question_text")
        if not question.get("question_type"):
            raise ValueError("LPP question is missing question_type")
        if not question.get("knowledge_points"):
            raise ValueError("LPP question is missing knowledge_points")


def build_learning_path_fields(result: dict[str, Any]) -> dict[str, Any]:
    """Map fixed P1-P5 runtime facts to SmartTutor's original path schema."""
    validate_lpp_result(result)
    questions = result["recommendation"]["questions"]
    purposes: dict[str, str] = {}
    for item in result.get("plan_items") or []:
        if not isinstance(item, dict):
            continue
        priority = str(item.get("priority") or "")
        purpose = str(item.get("purpose_and_effect") or "").strip()
        if priority and purpose:
            purposes[priority] = purpose

    stages: list[dict[str, Any]] = []
    main_path_sequence: list[str] = []
    milestones: list[str] = []
    for question in questions:
        order = int(question["order"])
        priority = f"P{order}"
        knowledge_points = question.get("knowledge_points") or []
        skills: list[dict[str, Any]] = []
        names: list[str] = []
        for point in knowledge_points:
            if not isinstance(point, dict):
                continue
            skill_id = str(
                point.get("knowledge_point_id")
                or point.get("skill_id")
                or ""
            )
            skill_name = str(
                point.get("knowledge_point_name")
                or point.get("skill_name")
                or f"知识点{skill_id}"
            )
            if skill_id and skill_id not in main_path_sequence:
                main_path_sequence.append(skill_id)
            names.append(skill_name)
            skills.append(
                {
                    "skill_id": skill_id,
                    "skill_name": skill_name,
                    "priority": "必学",
                    "estimated_time_min": 10,
                    "reason": purposes.get(
                        priority,
                        f"这是 LPP Runtime 固定推荐序列中的 {priority}。",
                    ),
                }
            )

        knowledge_label = "、".join(names) or "当前目标知识点"
        question_text = str(question["question_text"])
        stages.append(
            {
                "stage_id": priority,
                "name": f"{priority} · {knowledge_label}",
                "objective": f"完成并理解{question.get('question_type', '练习题')}所考查的{knowledge_label}",
                "skills": skills,
                "duration_min": 10,
                "checkpoints": [f"能够独立完成并解释：{question_text}"],
                "resources": [question_text],
                "expected_outcome": f"完成 {priority} 并能说明相关知识点的判断依据。",
            }
        )
        milestones.append(f"完成 {priority}：{knowledge_label}")

    total_time = f"约{sum(stage['duration_min'] for stage in stages)}分钟"
    return {
        "learning_path": stages,
        "stages": copy.deepcopy(stages),
        "total_estimated_time": total_time,
        "estimated_completion": total_time,
        "main_path_sequence": main_path_sequence,
        "optional_branch": [],
        "milestones": milestones,
        "recommended_questions": copy.deepcopy(questions),
        "target": copy.deepcopy(result.get("target")),
        "lpp_source": "lpp_runtime",
        "lpp_student_id": str(result.get("student_id") or ""),
    }


def _skill_root() -> Path:
    skill_path = Path(settings.lpp.skill_path)
    if not skill_path.is_absolute():
        repo_root = Path(__file__).resolve().parents[3]
        skill_path = repo_root / skill_path
    entrypoint = skill_path / "scripts" / "run_lpp.py"
    if not entrypoint.exists():
        raise RuntimeError(
            f"LPP Skill entrypoint not found: {entrypoint}. "
            "Check SMART_TUTOR_LPP__SKILL_PATH setting."
        )
    return skill_path.resolve()


async def _run_lpp_command(arguments: list[str]) -> LppRuntimeOutput:
    skill_root = _skill_root()
    kt_root = Path(settings.kt.skill_path)
    if not kt_root.is_absolute():
        kt_root = Path(__file__).resolve().parents[3] / kt_root
    environment = {
        **os.environ,
        "REKT_DEVICE": "cpu",
        "REKT_ALLOW_CPU_FALLBACK": "1",
        "KT_RUNTIME_SKILL_ROOT": str(kt_root.resolve()),
    }
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(skill_root / "scripts" / "run_lpp.py"),
        *arguments,
        cwd=str(skill_root),
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=settings.lpp.timeout_seconds,
        )
    except TimeoutError:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()
        raise RuntimeError(
            f"LPP Skill timed out after {settings.lpp.timeout_seconds} seconds"
        )

    raw_json = stdout.decode("utf-8", errors="replace").strip()
    stderr_text = stderr.decode("utf-8", errors="replace").strip()
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"LPP Skill returned invalid JSON: {stderr_text or raw_json[-1000:]}"
        ) from exc
    if process.returncode != 0:
        raise RuntimeError(
            f"LPP Skill exited with code {process.returncode}: "
            f"{data.get('message') or stderr_text}"
        )
    validate_lpp_result(data)
    return LppRuntimeOutput(data=data, raw_json=raw_json)


async def run_lpp_for_student(
    student_id: str,
    *,
    target_question_id: int | None = None,
    preferred_skill_ids: list[int] | None = None,
) -> LppRuntimeOutput | None:
    arguments = [
        "--student-id",
        str(student_id),
        "--length",
        str(settings.lpp.history_length),
        "--seed",
        str(settings.lpp.seed),
    ]
    if target_question_id is not None:
        arguments.extend(["--target-question-id", str(target_question_id)])
    elif preferred_skill_ids:
        arguments.extend(
            ["--preferred-skill-ids", ",".join(map(str, preferred_skill_ids))]
        )
    try:
        return await _run_lpp_command(arguments)
    except Exception as exc:
        logger.warning(
            "LPP planning failed for student=%s: %s: %s",
            student_id,
            type(exc).__name__,
            exc,
        )
        return None
