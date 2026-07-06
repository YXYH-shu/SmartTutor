from __future__ import annotations

import json
import os
from collections import Counter
from functools import lru_cache
from typing import Any

from kt_runtime.config import DEFAULT_REKT_DATA_DIR


KT_RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(KT_RUNTIME_DIR)
SKILL_ROOT = os.path.dirname(SCRIPTS_DIR)


def _backend(config: dict[str, Any]) -> str:
    runtime_cfg = config.get("runtime", {}) if isinstance(config, dict) else {}
    model_cfg = config.get("model", {}) if isinstance(config, dict) else {}
    return str(runtime_cfg.get("backend") or model_cfg.get("backend") or "rekt_cli").strip().lower()


def _is_rekt_json_backend(config: dict[str, Any]) -> bool:
    return _backend(config) in {"rekt_cli", "rekt_json", "rekt"}


def _rekt_data_dir(config: dict[str, Any]) -> str:
    rekt_cfg = config.get("rekt", {}) if isinstance(config, dict) else {}
    data_dir = str(rekt_cfg.get("data_dir") or DEFAULT_REKT_DATA_DIR)
    if os.path.isabs(data_dir):
        return data_dir
    return os.path.join(SKILL_ROOT, data_dir)


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _normalize_trace_item(item: dict[str, Any], index: int) -> dict[str, int]:
    if not isinstance(item, dict):
        raise ValueError(f"student_trace[{index}] must be an object.")
    if "skill_id" not in item or "correct" not in item:
        raise ValueError(f"student_trace[{index}] must contain skill_id and correct.")
    correct = int(item["correct"])
    if correct not in (0, 1):
        raise ValueError(f"student_trace[{index}].correct must be 0 or 1.")
    normalized = {
        "skill_id": int(item["skill_id"]),
        "correct": correct,
        "step": int(item.get("step", index + 1)),
    }
    if item.get("item_id") is not None:
        normalized["item_id"] = int(item["item_id"])
    return normalized


def _normalize_interaction(item: dict[str, Any], index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError(f"recent_interactions[{index}] must be an object.")
    return {
        "step": int(item.get("step", index + 1)),
        "skill_id": int(item["skill_id"]),
        "correct": int(item["correct"]),
        "knowledge_point_name": str(item.get("knowledge_point_name") or ""),
        "knowledge_point_description": str(item.get("knowledge_point_description") or ""),
        "topic_id": _int_or_none(item.get("topic_id")),
        "topic_name": str(item.get("topic_name") or ""),
        "domain_id": _int_or_none(item.get("domain_id")),
        "domain_name": str(item.get("domain_name") or ""),
        "skill_names": [str(value) for value in item.get("skill_names", []) if str(value).strip()],
        "question_id": int(item.get("question_id", 0)),
    }


def _normalize_kp_item(item: dict[str, Any], index: int) -> tuple[int, dict[str, Any]]:
    if not isinstance(item, dict):
        raise ValueError(f"kp catalog item {index} must be an object.")
    kp_id = int(item["kp_id"])
    return kp_id, {
        "kp_id": kp_id,
        "knowledge_point_name": str(item.get("knowledge_point_name") or ""),
        "knowledge_point_description": str(item.get("knowledge_point_description") or ""),
        "topic_id": _int_or_none(item.get("topic_id")),
        "topic_name": str(item.get("topic_name") or ""),
        "domain_id": _int_or_none(item.get("domain_id")),
        "domain_name": str(item.get("domain_name") or ""),
        "skill_names": [str(value) for value in item.get("skill_names", []) if str(value).strip()],
        "hit_count": int(item.get("hit_count", 0)),
        "question_count": int(item.get("question_count", 0)),
        "subject": str(item.get("subject") or ""),
        "grade_level": item.get("grade_level"),
        "cognitive_level": item.get("cognitive_level"),
    }


def _history_limit(config: dict[str, Any], history_limit: int | None) -> int:
    history_cfg = config.get("history", {})
    selection = str(history_cfg.get("selection", "recent")).strip().lower() or "recent"
    if history_limit is None:
        history_limit = int(history_cfg.get("max_interactions", 300))
    if selection == "all" or int(history_limit) <= 0:
        return 10000
    return int(history_limit)


def _rekt_history_limit(config: dict[str, Any], history_limit: int | None) -> int:
    limit = _history_limit(config, history_limit)
    rekt_cfg = config.get("rekt", {}) if isinstance(config, dict) else {}
    max_seq_len = int(rekt_cfg.get("max_seq_len") or 200)
    return min(limit, max_seq_len)


def _parse_rekt_skill_ids(value: Any) -> list[int]:
    if isinstance(value, list):
        return [int(skill_id) for skill_id in value]
    return [int(value)]


def _student_id_from_rekt(value: str) -> int:
    text = str(value).strip()
    if text.startswith("VSTU"):
        return int(text[4:])
    return int(text)


def _load_rekt_knowledges(data_dir: str) -> dict[int, dict[str, Any]]:
    knowledge_path = os.path.join(data_dir, "knowledges.json")
    if not os.path.exists(knowledge_path):
        return {}

    with open(knowledge_path, "r", encoding="utf-8") as file_obj:
        payload = json.load(file_obj)

    if not isinstance(payload, list):
        raise ValueError("knowledges.json must contain a JSON array.")

    rows: dict[int, dict[str, Any]] = {}
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"knowledges.json[{index}] must be an object.")
        kp_id = int(item["id"])
        rows[kp_id] = {
            "knowledge_point_name": str(item.get("name") or ""),
            "knowledge_point_description": str(item.get("description") or ""),
            "topic_id": _int_or_none(item.get("topic_id")),
            "domain_id": _int_or_none(item.get("domain_id")),
            "grade_level": item.get("grade_name"),
        }
    return rows


@lru_cache(maxsize=4)
def _load_rekt_json_data(data_dir: str) -> dict[str, Any]:
    exercises: dict[int, dict[str, Any]] = {}
    catalog: dict[int, dict[str, Any]] = {}
    question_counts: Counter[int] = Counter()
    hit_counts: Counter[int] = Counter()
    student_records: dict[int, list[dict[str, int]]] = {}

    exercise_path = os.path.join(data_dir, "exercise_info.json")
    with open(exercise_path, "r", encoding="utf-8") as file_obj:
        for line in file_obj:
            if not line.strip():
                continue
            item = json.loads(line)
            question_id = int(item["question_id"])
            skill_ids = _parse_rekt_skill_ids(item["kp_id"])
            primary_skill_id = int(skill_ids[0])
            exercises[question_id] = {
                "question_id": question_id,
                "skill_ids": skill_ids,
                "primary_skill_id": primary_skill_id,
                "question_desc": str(item.get("question_desc") or ""),
                "kp_desc": str(item.get("kp_desc") or f"知识点 {primary_skill_id}"),
                "topic_id": _int_or_none(item.get("topic_id")),
                "topic_name": str(item.get("topic_desc") or ""),
                "grade_level": item.get("grade"),
            }
            for skill_id in skill_ids:
                question_counts[skill_id] += 1
                catalog.setdefault(
                    skill_id,
                    {
                        "kp_id": skill_id,
                        "knowledge_point_name": str(item.get("kp_desc") or f"知识点 {skill_id}"),
                        "knowledge_point_description": "",
                        "topic_id": _int_or_none(item.get("topic_id")),
                        "topic_name": str(item.get("topic_desc") or ""),
                        "domain_id": None,
                        "domain_name": "",
                        "skill_names": [],
                        "hit_count": 0,
                        "question_count": 0,
                        "subject": "",
                        "grade_level": item.get("grade"),
                        "cognitive_level": None,
                    },
                )

    record_path = os.path.join(data_dir, "student_record.json")
    with open(record_path, "r", encoding="utf-8") as file_obj:
        for line in file_obj:
            if not line.strip():
                continue
            item = json.loads(line)
            user_id = int(item["student_id"])
            rows: list[dict[str, int]] = []
            for question_id_raw, correct_raw in zip(item.get("question_id", []), item.get("is_corrects", [])):
                question_id = int(question_id_raw)
                exercise = exercises.get(question_id)
                if exercise is None:
                    continue
                skill_id = int(exercise["primary_skill_id"])
                correct = int(correct_raw)
                rows.append({"skill_id": skill_id, "correct": correct, "item_id": question_id})
                hit_counts[skill_id] += 1
            student_records[user_id] = rows

    for skill_id, row in catalog.items():
        row["question_count"] = int(question_counts[skill_id])
        row["hit_count"] = int(hit_counts[skill_id])

    knowledge_rows = _load_rekt_knowledges(data_dir)
    for skill_id, meta in knowledge_rows.items():
        if skill_id not in catalog:
            catalog[skill_id] = {
                "kp_id": skill_id,
                "knowledge_point_name": f"知识点 {skill_id}",
                "knowledge_point_description": "",
                "topic_id": None,
                "topic_name": "",
                "domain_id": None,
                "domain_name": "",
                "skill_names": [],
                "hit_count": 0,
                "question_count": 0,
                "subject": "",
                "grade_level": None,
                "cognitive_level": None,
            }
        row = catalog[skill_id]
        if meta.get("knowledge_point_name"):
            row["knowledge_point_name"] = meta["knowledge_point_name"]
        if meta.get("knowledge_point_description"):
            row["knowledge_point_description"] = meta["knowledge_point_description"]
        if meta.get("topic_id") is not None:
            row["topic_id"] = meta["topic_id"]
        if meta.get("domain_id") is not None:
            row["domain_id"] = meta["domain_id"]
        if meta.get("grade_level"):
            row["grade_level"] = meta["grade_level"]

    max_skill_id = max(catalog) if catalog else 0
    return {
        "exercises": exercises,
        "catalog": catalog,
        "student_records": student_records,
        "max_skill_id": max_skill_id,
    }


def _fetch_rekt_json_student_history(
    config: dict[str, Any],
    student_id: str,
    history_limit: int | None = None,
) -> dict[str, Any]:
    data = _load_rekt_json_data(_rekt_data_dir(config))
    user_id = _student_id_from_rekt(student_id)
    if user_id not in data["student_records"]:
        raise KeyError(f"student_id {student_id} not found in ReKT JSON dataset")

    all_records = data["student_records"][user_id]
    limit = _rekt_history_limit(config, history_limit)
    start_index = max(0, len(all_records) - limit)
    records = all_records[start_index:]
    trace = [
        {
            "skill_id": int(item["skill_id"]),
            "correct": int(item["correct"]),
            "step": start_index + index + 1,
            "item_id": int(item["item_id"]),
        }
        for index, item in enumerate(records)
    ]

    exercises = data["exercises"]
    catalog = data["catalog"]
    interactions = []
    for item in trace:
        exercise = exercises.get(int(item["item_id"]), {})
        meta = catalog.get(int(item["skill_id"]), {})
        interactions.append(
            {
                "step": int(item["step"]),
                "skill_id": int(item["skill_id"]),
                "correct": int(item["correct"]),
                "knowledge_point_name": str(
                    meta.get("knowledge_point_name")
                    or exercise.get("kp_desc")
                    or f"知识点 {item['skill_id']}"
                ),
                "knowledge_point_description": str(meta.get("knowledge_point_description") or ""),
                "topic_id": exercise.get("topic_id"),
                "topic_name": str(exercise.get("topic_name") or ""),
                "domain_id": meta.get("domain_id"),
                "domain_name": "",
                "skill_names": [],
                "question_id": int(item["item_id"]),
            }
        )

    recent_window = max(1, int(config.get("analysis", {}).get("recent_window", 20)))
    summary = summarize_trace(trace, recent_window, data["catalog"])
    return {
        "source_mode": "rekt_json",
        "student_id": str(user_id),
        "student_name": f"ReKTStudent{user_id:06d}",
        "grade_level": None,
        "student_trace": trace,
        "recent_interactions": interactions[-recent_window:],
        "summary": summary,
    }


def load_kp_catalog_from_config(config: dict[str, Any]) -> dict[int, dict[str, Any]]:
    if not _is_rekt_json_backend(config):
        raise ValueError("Only REKT local dataset backend is supported.")
    catalog = _load_rekt_json_data(_rekt_data_dir(config))["catalog"]
    return {
        int(skill_id): dict(row)
        for skill_id, row in catalog.items()
        if int(row.get("question_count") or 0) > 0
    }


def load_kp_catalog(_ignored_records_path: str | None = None) -> dict[int, dict[str, Any]]:
    from kt_runtime.config import load_runtime_config

    return load_kp_catalog_from_config(load_runtime_config(None))


def infer_num_skills(config: dict[str, Any]) -> int:
    if not _is_rekt_json_backend(config):
        raise ValueError("Only REKT local dataset backend is supported.")
    num_skills = int(_load_rekt_json_data(_rekt_data_dir(config))["max_skill_id"])
    if num_skills > 0:
        return num_skills
    raise RuntimeError("REKT JSON exercise_info 未提供有效 kp_id。")


def summarize_trace(
    student_trace: list[dict[str, Any]],
    recent_window: int,
    catalog: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    recent_window = max(1, int(recent_window))
    recent_slice = student_trace[-recent_window:]
    counter = Counter(int(item["skill_id"]) for item in student_trace)
    total = len(student_trace)
    correct_count = sum(int(item["correct"]) for item in student_trace)

    top_skills = []
    for skill_id, count in counter.most_common(10):
        meta = catalog.get(skill_id, {})
        top_skills.append(
            {
                "skill_id": int(skill_id),
                "count": int(count),
                "name": str(meta.get("knowledge_point_name") or f"知识点 {skill_id}"),
            }
        )

    return {
        "history_length": total,
        "correct_count": correct_count,
        "accuracy": (correct_count / total) if total else 0.0,
        "recent_window": recent_window,
        "recent_accuracy": (
            sum(int(item["correct"]) for item in recent_slice) / len(recent_slice)
            if recent_slice
            else 0.0
        ),
        "top_skills": top_skills,
    }


def fetch_student_history(
    config: dict[str, Any],
    student_id: str,
    history_limit: int | None = None,
) -> dict[str, Any]:
    if not _is_rekt_json_backend(config):
        raise ValueError("Only REKT local dataset backend is supported.")
    return _fetch_rekt_json_student_history(config, student_id, history_limit)
