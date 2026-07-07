from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from kt_runtime.config import load_runtime_config
from kt_runtime.student_source import (
    fetch_student_history,
    infer_num_skills,
    load_kp_catalog_from_config,
    summarize_trace,
)


def parse_trace_json(raw_trace_json: str) -> list[dict[str, int]]:
    payload = json.loads(raw_trace_json)
    if not isinstance(payload, list):
        raise ValueError("student_trace JSON must be a list.")
    student_trace: list[dict[str, int]] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"student_trace[{index}] must be an object.")
        if "skill_id" not in item or "correct" not in item:
            raise ValueError(f"student_trace[{index}] must contain skill_id and correct.")
        trace_item = {"skill_id": int(item["skill_id"]), "correct": int(item["correct"])}
        if item.get("item_id") is not None:
            trace_item["item_id"] = int(item["item_id"])
        student_trace.append(trace_item)
    return student_trace


def parse_trace_pairs(raw_trace_pairs: str) -> list[dict[str, int]]:
    student_trace: list[dict[str, int]] = []
    for index, pair in enumerate(raw_trace_pairs.split(","), start=1):
        chunk = pair.strip()
        if not chunk:
            continue
        try:
            skill_text, correct_text = chunk.split(":", 1)
        except ValueError as exc:
            raise ValueError(
                f"Invalid trace pair {chunk!r}. Expected format like 27:1,13:0."
            ) from exc
        student_trace.append(
            {"skill_id": int(skill_text.strip()), "correct": int(correct_text.strip())}
        )
    if not student_trace:
        raise ValueError("No valid trace pairs were provided.")
    return student_trace


def parse_targets(raw_targets: str | None, num_skills: int, config: dict[str, Any]) -> list[int]:
    raw_targets = raw_targets or str(config.get("prediction", {}).get("default_targets", "all"))
    if raw_targets == "all":
        return sorted(load_kp_catalog_from_config(config))

    predictable_targets = set(load_kp_catalog_from_config(config))
    targets: list[int] = []
    for part in raw_targets.split(","):
        part = part.strip()
        if not part:
            continue
        skill_id = int(part)
        if not 1 <= skill_id <= num_skills:
            raise ValueError(f"target skill_id must be in [1, {num_skills}], got {skill_id}.")
        if skill_id not in predictable_targets:
            raise ValueError(f"target skill_id {skill_id} has no REKT question mapping.")
        targets.append(skill_id)
    if not targets:
        raise ValueError("No valid targets were provided.")
    return targets


def rekt_skill_arg(raw_targets: str | None, config: dict[str, Any], targets: list[int]) -> str:
    configured_targets = str(config.get("prediction", {}).get("default_targets", "all"))
    effective_targets = raw_targets or configured_targets
    if str(effective_targets).strip().lower() == "all":
        return "all"
    return ",".join(str(int(target)) for target in targets)


def _build_analysis_context(
    source_mode: str,
    student_trace: list[dict[str, int]],
    config: dict[str, Any],
    *,
    initial_query: str | None = None,
    history_context: str | None = None,
    student_profile: dict[str, Any] | None = None,
    summary: dict[str, Any] | None = None,
    recent_interactions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if summary is None:
        catalog = load_kp_catalog_from_config(config)
        summary = summarize_trace(
            student_trace,
            recent_window=int(config.get("analysis", {}).get("recent_window", 20)),
            catalog=catalog,
        )
    return {
        "initial_query": initial_query or "",
        "history_context": history_context or "",
        "trace_source": source_mode,
        "runtime_config_path": config.get("_meta", {}).get("config_path"),
        "student_profile": student_profile or {},
        "sequence_summary": summary,
        "recent_interactions": recent_interactions or [],
    }


def build_request_from_trace(
    student_trace: list[dict[str, int]],
    *,
    raw_targets: str | None = None,
    config_path: str | None = None,
    request_id: str | None = None,
    device: str | None = None,
    initial_query: str | None = None,
    history_context: str | None = None,
    source_mode: str = "manual_trace",
) -> dict[str, Any]:
    config = load_runtime_config(config_path)
    num_skills = infer_num_skills(config)
    targets = parse_targets(raw_targets, num_skills, config)
    cli_skill_arg = rekt_skill_arg(raw_targets, config, targets)
    if request_id is None:
        request_id = f"{source_mode}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    return {
        "request_id": request_id,
        "task": "predict_correctness",
        "student_trace": student_trace,
        "targets": [{"skill_id": target} for target in targets],
        "rekt_skill_arg": cli_skill_arg,
        "device": device or str(config.get("runtime", {}).get("device", "cuda:0")),
        "analysis_enabled": bool(config.get("analysis", {}).get("enabled", True)),
        "analysis_context": _build_analysis_context(
            source_mode=source_mode,
            student_trace=student_trace,
            config=config,
            initial_query=initial_query,
            history_context=history_context,
        ),
    }


def build_request_from_student_id(
    student_id: str,
    *,
    raw_targets: str | None = None,
    config_path: str | None = None,
    request_id: str | None = None,
    device: str | None = None,
    history_limit: int | None = None,
    initial_query: str | None = None,
    history_context: str | None = None,
) -> dict[str, Any]:
    config = load_runtime_config(config_path)
    bundle = fetch_student_history(config, student_id, history_limit=history_limit)
    student_trace = [
        {
            **({"item_id": int(item["item_id"])} if item.get("item_id") is not None else {}),
            "skill_id": int(item["skill_id"]),
            "correct": int(item["correct"]),
        }
        for item in bundle["student_trace"]
    ]
    num_skills = infer_num_skills(config)
    targets = parse_targets(raw_targets, num_skills, config)
    cli_skill_arg = rekt_skill_arg(raw_targets, config, targets)
    if request_id is None:
        request_id = f"student-{student_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    return {
        "request_id": request_id,
        "task": "predict_correctness",
        "student_trace": student_trace,
        "targets": [{"skill_id": target} for target in targets],
        "rekt_skill_arg": cli_skill_arg,
        "device": device or str(config.get("runtime", {}).get("device", "cuda:0")),
        "analysis_enabled": bool(config.get("analysis", {}).get("enabled", True)),
        "analysis_context": _build_analysis_context(
            source_mode="student_id",
            student_trace=student_trace,
            config=config,
            initial_query=initial_query,
            history_context=history_context,
            student_profile={
                "student_id": bundle["student_id"],
                "student_name": bundle["student_name"],
                "grade_level": bundle["grade_level"],
            },
            summary=bundle["summary"],
            recent_interactions=bundle["recent_interactions"],
        ),
    }
