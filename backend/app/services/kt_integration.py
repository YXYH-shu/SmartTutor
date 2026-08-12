"""KT (Knowledge Tracing) 集成适配器。

把 services/kt-runtime-skill 的 REKT 推理能力接入到 backend 的 cognitive_diagnosis
agent。集成模式(integrated)下,cognitive_diagnosis 会优先调用本模块拿到真实的
知识点掌握度,然后 LLM 只负责生成认知归因和自然语言解读。

设计原则:
1. KT 是 ground truth — mastery 数值不交给 LLM 重写
2. 失败可降级 — KT 异常时返回 None,调用方可继续走纯 LLM 路径
3. 路径隔离 — kt_runtime 模块只在第一次调用时被加入 sys.path
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import signal
import sys
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_KT_PATH_INITIALIZED = False


def _kt_skill_root() -> Path:
    skill_path = Path(settings.kt.skill_path)
    if not skill_path.is_absolute():
        repo_root = Path(__file__).resolve().parents[3]
        skill_path = repo_root / skill_path
    entrypoint = skill_path / "scripts" / "run_kt.py"
    if not entrypoint.exists():
        raise RuntimeError(
            f"KT Skill entrypoint not found: {entrypoint}. "
            "Check SMART_TUTOR_KT__SKILL_PATH setting."
        )
    return skill_path.resolve()


def _numeric_student_id(value: Any) -> str | None:
    """Return a dataset student ID and ignore SmartTutor UUID values."""
    if isinstance(value, bool) or value is None:
        return None
    text = str(value).strip()
    return text if text.isdigit() else None


def resolve_kt_student_id(
    input_data: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> str | None:
    """Resolve REKT/LPP student ID without treating the app UUID as a dataset ID."""
    context = context or {}

    for value in (
        input_data.get("kt_student_id"),
        input_data.get("student_id"),
        context.get("kt_student_id"),
        context.get("student_id"),
    ):
        resolved = _numeric_student_id(value)
        if resolved:
            return resolved

    current_message = str(
        input_data.get("current_message")
        or input_data.get("message")
        or ""
    )
    match = re.search(
        r"(?:学生|student)\s*#?\s*(\d+)",
        current_message,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1)

    profile = input_data.get("user_profile") or context.get("user_profile") or {}
    if isinstance(profile, dict):
        preferences = profile.get("preferences") or {}
        if isinstance(preferences, dict):
            resolved = _numeric_student_id(preferences.get("kt_student_id"))
            if resolved:
                return resolved

    return _numeric_student_id(settings.kt.demo_student_id)


def _ensure_kt_path() -> None:
    """把 services/kt-runtime-skill/scripts 加到 sys.path,使 kt_runtime 可被 import。"""
    global _KT_PATH_INITIALIZED
    if _KT_PATH_INITIALIZED:
        return

    # settings.kt.skill_path 是相对于仓库根目录或绝对路径
    skill_path = _kt_skill_root()
    scripts_dir = skill_path / "scripts"
    abs_path = str(scripts_dir.resolve())
    if abs_path not in sys.path:
        sys.path.insert(0, abs_path)
    _KT_PATH_INITIALIZED = True
    logger.info("KT skill path initialized: %s", abs_path)


_MAX_SELECTED_KNOWLEDGE_POINTS = 18


def _selected_skill_ids(raw: dict[str, Any]) -> list[str]:
    """Read the original skill's relevance-ranked Top-18 IDs in order."""
    analysis = raw.get("llm_analysis")
    selected = (
        analysis.get("selected_knowledge_points")
        if isinstance(analysis, dict)
        else None
    )
    if not isinstance(selected, list):
        return []

    skill_ids: list[str] = []
    seen: set[str] = set()
    for item in selected:
        if not isinstance(item, dict):
            continue
        skill_id = item.get("source_skill_id", item.get("skill_id"))
        if skill_id is None:
            continue
        normalized = str(skill_id).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            skill_ids.append(normalized)
        if len(skill_ids) >= _MAX_SELECTED_KNOWLEDGE_POINTS:
            break
    return skill_ids


def _normalize_kt_output(raw: dict[str, Any]) -> dict[str, Any]:
    """把 KTPredictResponse 输出转成 cognitive_diagnosis agent 期望的 schema。

    返回字段与现有 cognitive_diagnosis.yaml 的 output_schema 对齐:
    - knowledge_states: list[{skill_id, skill_name, mastery_percent, mastery_rate, status, evidence}]
    - mastery_rates: dict[str, float]  (skill_id → 0..1)
    - weak_points: list[dict]  (status == "weak" 的子集)
    - diagnosis_source: "kt_rekt"  (标记数据来源,LLM 不可改写)
    - metrics, model_info, llm_analysis: KT 原始字段,供下游/前端展示
    """
    predictions = [
        prediction
        for prediction in (raw.get("predictions", []) or [])
        if isinstance(prediction, dict)
    ]
    selected_ids = _selected_skill_ids(raw)
    if selected_ids:
        predictions_by_skill_id = {
            str((prediction.get("target") or {}).get("skill_id", "")): prediction
            for prediction in predictions
        }
        predictions = [
            predictions_by_skill_id[skill_id]
            for skill_id in selected_ids
            if skill_id in predictions_by_skill_id
        ]
    else:
        logger.warning(
            "KT result did not include skill-selected knowledge points; "
            "using a bounded %d-item fallback",
            _MAX_SELECTED_KNOWLEDGE_POINTS,
        )
        predictions = predictions[:_MAX_SELECTED_KNOWLEDGE_POINTS]
    knowledge_states: list[dict[str, Any]] = []
    mastery_rates: dict[str, float] = {}
    weak_points: list[dict[str, Any]] = []

    for pred in predictions:
        target = pred.get("target", {}) or {}
        skill_id = str(target.get("skill_id", ""))
        prob = pred.get("probability_correct")
        if prob is None or not skill_id:
            continue

        try:
            prob_float = float(prob)
        except (TypeError, ValueError):
            continue

        # 0..1 区间,裁剪异常值
        prob_float = max(0.0, min(1.0, prob_float))
        mastery_pct = round(prob_float * 100, 1)
        if prob_float >= 0.7:
            status = "mastered"
        elif prob_float >= 0.4:
            status = "developing"
        else:
            status = "weak"

        extras = {
            **(pred.get("extras", {}) or {}),
            **(target.get("extras", {}) or {}),
        }
        skill_name = (
            extras.get("knowledge_point_name")
            or extras.get("kp_desc")
            or extras.get("name")
            or f"KP{skill_id}"
        )
        skill_type = extras.get("knowledge_point_type") or extras.get("type")
        if skill_type not in {"概念", "规律", "方法", "价值"}:
            skill_type = "概念"

        ks = {
            "skill_id": skill_id,
            "skill_name": skill_name,
            "type": skill_type,
            "mastery_percent": f"{mastery_pct}%",
            "mastery_rate": prob_float,
            "status": status,
            "mastery_label": _mastery_label(prob_float),
            "evidence": extras.get("evidence", "REKT 模型预测"),
        }
        knowledge_states.append(ks)
        mastery_rates[skill_id] = prob_float
        if status == "weak":
            weak_points.append(ks)

    return {
        "knowledge_states": knowledge_states,
        "mastery_rates": mastery_rates,
        "weak_points": weak_points,
        "metrics": raw.get("metrics", {}) or {},
        "model_info": raw.get("model_info", {}) or {},
        "llm_analysis": raw.get("llm_analysis"),
        "diagnosis_source": "kt_rekt",
    }


def _mastery_label(probability: float) -> str:
    if probability < 0.2:
        return "极低"
    if probability < 0.4:
        return "较低"
    if probability < 0.6:
        return "中等"
    if probability < 0.8:
        return "较好"
    return "良好"


_KT_PROMPT_STATE_FIELDS = (
    "skill_id",
    "skill_name",
    "type",
    "mastery_percent",
    "mastery_rate",
    "mastery_label",
    "status",
    "evidence",
)


def _prompt_mastery_rate(state: dict[str, Any]) -> float:
    try:
        return float(state.get("mastery_rate", 1.0))
    except (TypeError, ValueError):
        return 1.0


def build_kt_prompt_context(kt_result: dict[str, Any]) -> dict[str, Any]:
    """Project complete KT facts to the bounded subset needed for LLM attribution."""
    states = [
        state
        for state in (kt_result.get("knowledge_states") or [])
        if isinstance(state, dict)
    ]
    grouped = {
        status: [state for state in states if state.get("status") == status]
        for status in ("weak", "developing", "mastered")
    }
    grouped["weak"].sort(key=_prompt_mastery_rate)
    grouped["developing"].sort(key=_prompt_mastery_rate)
    grouped["mastered"].sort(key=_prompt_mastery_rate, reverse=True)

    selected: list[dict[str, Any]] = []
    seen_skill_ids: set[str] = set()
    for status, limit in (("weak", 10), ("developing", 5), ("mastered", 3)):
        for state in grouped[status]:
            skill_id = str(state.get("skill_id") or state.get("skill_name") or "")
            if not skill_id or skill_id in seen_skill_ids:
                continue
            seen_skill_ids.add(skill_id)
            selected.append(
                {
                    field: state[field]
                    for field in _KT_PROMPT_STATE_FIELDS
                    if field in state
                }
            )
            if sum(item.get("status") == status for item in selected) >= limit:
                break

    return {
        "total_count": len(states),
        "weak_count": len(grouped["weak"]),
        "developing_count": len(grouped["developing"]),
        "mastered_count": len(grouped["mastered"]),
        "priority_states": selected,
    }


async def _run_kt_command(arguments: list[str]) -> dict[str, Any]:
    """Run the KT CLI without blocking the event loop and enforce its timeout."""
    skill_root = _kt_skill_root()
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(skill_root / "scripts" / "run_kt.py"),
        *arguments,
        cwd=str(skill_root),
        env=os.environ.copy(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=settings.kt.timeout_seconds,
        )
    except TimeoutError:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()
        raise RuntimeError(
            f"KT Skill timed out after {settings.kt.timeout_seconds} seconds"
        )

    raw_json = stdout.decode("utf-8", errors="replace").strip()
    stderr_text = stderr.decode("utf-8", errors="replace").strip()
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"KT Skill returned invalid JSON: {stderr_text or raw_json[-1000:]}"
        ) from exc
    if process.returncode != 0 or data.get("status") != "ok":
        raise RuntimeError(
            f"KT Skill exited with code {process.returncode}: "
            f"{data.get('message') or stderr_text}"
        )
    return data


async def run_kt_for_student(
    student_id: str,
    *,
    targets: str | None = None,
    history_limit: int | None = None,
    initial_query: str | None = None,
    history_context: str | None = None,
) -> dict[str, Any] | None:
    """按学生 ID 调用 KT runtime,返回标准化诊断结果。

    Args:
        student_id: 学生 ID(REKT 数据集里的索引,如 "40")
        targets: 可选,逗号分隔的预测目标 kp_id;留空则用 settings.kt.default_targets 或 kt config 默认
        history_limit: 历史序列截断长度
        initial_query: 学生当前问题,传给分析报告
        history_context: 额外历史上下文(如"学生最近在学电路")

    Returns:
        标准化的诊断 dict;KT 调用失败时返回 None,调用方应降级到纯 LLM
    """
    try:
        arguments = [
            "--student-id",
            str(student_id),
            "--device",
            settings.kt.device,
        ]
        raw_targets = targets or settings.kt.default_targets
        if raw_targets:
            arguments.extend(["--targets", str(raw_targets)])
        if history_limit is not None:
            arguments.extend(["--history-limit", str(history_limit)])
        if initial_query:
            arguments.extend(["--initial-query", str(initial_query)])
        if history_context:
            arguments.extend(["--history-context", str(history_context)])

        data = await _run_kt_command(arguments)
        normalized = _normalize_kt_output(data)
        logger.info(
            "KT diagnosis succeeded for student=%s: %d kps (%d weak)",
            student_id,
            len(normalized["knowledge_states"]),
            len(normalized["weak_points"]),
        )
        return normalized
    except Exception as exc:
        logger.warning(
            "KT diagnosis failed for student=%s: %s: %s",
            student_id,
            type(exc).__name__,
            exc,
        )
        return None


async def run_kt_for_trace(
    trace: list[dict[str, Any]],
    *,
    targets: list[dict[str, Any]] | None = None,
    initial_query: str | None = None,
) -> dict[str, Any] | None:
    """按手工输入的 student_trace 调用 KT(用于实时交互场景,不依赖固定数据集)。

    Args:
        trace: [{skill_id, correct, item_id?, timestamp?}, ...]
        targets: [{skill_id, ...}, ...];留空时由 kt config 决定
        initial_query: 学生当前问题

    Returns:
        同 run_kt_for_student
    """
    try:
        _ensure_kt_path()
        from kt_runtime.api import predict_from_dict

        payload = {
            "request_id": f"backend-{id(trace)}",
            "task": "predict_correctness",
            "student_trace": trace,
            "targets": targets or [],
            "device": settings.kt.device,
            "analysis_enabled": True,
            "analysis_context": {"initial_query": initial_query or ""},
        }
        response = predict_from_dict(payload)
        data = response.to_dict() if hasattr(response, "to_dict") else response
        return _normalize_kt_output(data)
    except Exception as exc:
        logger.warning(
            "KT diagnosis failed for trace (%d items): %s: %s",
            len(trace),
            type(exc).__name__,
            exc,
        )
        return None
