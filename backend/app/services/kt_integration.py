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

import logging
import sys
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_KT_PATH_INITIALIZED = False


def _ensure_kt_path() -> None:
    """把 services/kt-runtime-skill/scripts 加到 sys.path,使 kt_runtime 可被 import。"""
    global _KT_PATH_INITIALIZED
    if _KT_PATH_INITIALIZED:
        return

    # settings.kt.skill_path 是相对于仓库根目录或绝对路径
    skill_path = Path(settings.kt.skill_path)
    if not skill_path.is_absolute():
        # backend/app/services/ → 上溯 4 层到仓库根
        repo_root = Path(__file__).resolve().parents[3]
        skill_path = repo_root / skill_path
    scripts_dir = skill_path / "scripts"
    if not scripts_dir.exists():
        raise RuntimeError(
            f"KT skill scripts directory not found: {scripts_dir}. "
            f"Check SMART_TUTOR_KT__SKILL_PATH setting."
        )
    abs_path = str(scripts_dir.resolve())
    if abs_path not in sys.path:
        sys.path.insert(0, abs_path)
    _KT_PATH_INITIALIZED = True
    logger.info("KT skill path initialized: %s", abs_path)


def _normalize_kt_output(raw: dict[str, Any]) -> dict[str, Any]:
    """把 KTPredictResponse 输出转成 cognitive_diagnosis agent 期望的 schema。

    返回字段与现有 cognitive_diagnosis.yaml 的 output_schema 对齐:
    - knowledge_states: list[{skill_id, skill_name, mastery_percent, mastery_rate, status, evidence}]
    - mastery_rates: dict[str, float]  (skill_id → 0..1)
    - weak_points: list[dict]  (status == "weak" 的子集)
    - diagnosis_source: "kt_rekt"  (标记数据来源,LLM 不可改写)
    - metrics, model_info, llm_analysis: KT 原始字段,供下游/前端展示
    """
    predictions = raw.get("predictions", []) or []
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

        extras = target.get("extras", {}) or {}
        skill_name = (
            extras.get("knowledge_point_name")
            or extras.get("kp_desc")
            or extras.get("name")
            or f"KP{skill_id}"
        )

        ks = {
            "skill_id": skill_id,
            "skill_name": skill_name,
            "mastery_percent": f"{mastery_pct}%",
            "mastery_rate": prob_float,
            "status": status,
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
        _ensure_kt_path()
        from kt_runtime.api import predict_from_student_id

        raw_targets = targets or settings.kt.default_targets or None
        response = predict_from_student_id(
            student_id=str(student_id),
            raw_targets=raw_targets,
            device=settings.kt.device,
            history_limit=history_limit,
            initial_query=initial_query,
            history_context=history_context,
        )
        data = response.to_dict() if hasattr(response, "to_dict") else response
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
