from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

from kt_runtime.analysis_report import attach_analysis_report
from kt_runtime.config import (
    DEFAULT_KT_CHECKPOINT_PATH,
    DEFAULT_KT_CLI_PATH,
    DEFAULT_KT_DATA_DIR,
    SKILL_ROOT,
    load_runtime_config,
)
from kt_runtime.contracts import KTPredictRequest, KTPredictResponse, Prediction


def predict_via_kt_cli(payload: dict[str, Any]) -> KTPredictResponse:
    request = KTPredictRequest.from_dict(payload)
    config = load_runtime_config(_config_path_from_payload(payload))
    response = _run_kt_cli(payload, request, config)
    if not request.analysis_enabled or payload.get("analysis_enabled") is False:
        return response
    return attach_analysis_report(payload, request, response)


def _config_path_from_payload(payload: dict[str, Any]) -> str | None:
    analysis_context = payload.get("analysis_context", {})
    if isinstance(analysis_context, dict) and analysis_context.get("runtime_config_path"):
        return str(analysis_context["runtime_config_path"])
    if payload.get("runtime_config_path"):
        return str(payload["runtime_config_path"])
    return None


def _student_id_from_payload(payload: dict[str, Any]) -> str:
    for key in ("student_id", "user_id"):
        if payload.get(key) not in (None, ""):
            return str(payload[key])

    analysis_context = payload.get("analysis_context", {})
    if isinstance(analysis_context, dict):
        profile = analysis_context.get("student_profile", {})
        if isinstance(profile, dict):
            for key in ("student_id", "user_id"):
                if profile.get(key) not in (None, ""):
                    return str(profile[key])

    raise ValueError("KT CLI execution requires a student_id.")


def _kt_cli_path(config: dict[str, Any]) -> str:
    kt_cfg = config.get("kt", {}) if isinstance(config, dict) else {}
    return _skill_relative_path(kt_cfg.get("cli_path") or DEFAULT_KT_CLI_PATH)


def _kt_data_dir(config: dict[str, Any]) -> str:
    kt_cfg = config.get("kt", {}) if isinstance(config, dict) else {}
    return _skill_relative_path(kt_cfg.get("data_dir") or DEFAULT_KT_DATA_DIR)


def _kt_checkpoint(config: dict[str, Any]) -> str:
    kt_cfg = config.get("kt", {}) if isinstance(config, dict) else {}
    return _skill_relative_path(kt_cfg.get("checkpoint_path") or DEFAULT_KT_CHECKPOINT_PATH)


def _skill_relative_path(path: Any) -> str:
    path_text = str(path or "").strip()
    if not path_text:
        return path_text
    if os.path.isabs(path_text):
        return path_text
    return os.path.abspath(os.path.join(SKILL_ROOT, path_text))


def _history_limit(payload: dict[str, Any], config: dict[str, Any]) -> int | None:
    kt_cfg = config.get("kt", {}) if isinstance(config, dict) else {}
    if payload.get("history_limit") is not None:
        limit = int(payload["history_limit"])
        max_seq_len = int(kt_cfg.get("max_seq_len") or limit)
        return min(limit, max_seq_len)
    if kt_cfg.get("history_limit") is not None:
        limit = int(kt_cfg["history_limit"])
        max_seq_len = int(kt_cfg.get("max_seq_len") or limit)
        return min(limit, max_seq_len)
    return None


def _target_skill_arg(payload: dict[str, Any], request: KTPredictRequest) -> str:
    raw_arg = str(payload.get("kt_skill_arg") or "").strip()
    if raw_arg:
        return raw_arg
    return ",".join(str(int(target.skill_id)) for target in request.targets)


def _run_kt_cli(
    payload: dict[str, Any],
    request: KTPredictRequest,
    config: dict[str, Any],
) -> KTPredictResponse:
    cli_path = _kt_cli_path(config)
    data_dir = _kt_data_dir(config)
    checkpoint = _kt_checkpoint(config)
    device = request.device or str(config.get("runtime", {}).get("device") or "cuda:0")
    history_limit = _history_limit(payload, config)
    student_id = _student_id_from_payload(payload)

    command = [
        sys.executable,
        cli_path,
        "--user_id",
        student_id,
        "--skill_id",
        _target_skill_arg(payload, request),
        "--data_dir",
        data_dir,
        "--checkpoint",
        checkpoint,
        "--device",
        device,
    ]
    if history_limit is not None:
        command.extend(["--history_limit", str(history_limit)])

    env = os.environ.copy()
    allow_cpu_fallback = bool(config.get("kt", {}).get("allow_cpu_fallback", False))
    env["KT_ALLOW_CPU_FALLBACK"] = "1" if allow_cpu_fallback else "0"

    completed = subprocess.run(
        command,
        cwd=os.path.dirname(cli_path),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"KT CLI failed with exit code {completed.returncode}: {message}")

    rows = parse_kt_json_lines(completed.stdout)
    predictions = _predictions_from_kt_rows(request, rows)
    missing_targets = _missing_prediction_targets(request, rows)
    return KTPredictResponse(
        request_id=request.request_id,
        status="ok",
        task=request.task,
        message="ok",
        predictions=predictions,
        metrics={
            "num_predictions": len(predictions),
            "kt_rows": len(rows),
            "missing_prediction_targets": missing_targets,
        },
        model_info={
            "model_type": "kt_cli",
            "source_project": "kt",
            "cli_path": cli_path,
            "data_dir": data_dir,
            "checkpoint_path": checkpoint,
            "device": device,
            "allow_cpu_fallback": allow_cpu_fallback,
            "history_limit": history_limit,
            "kt_skill_arg": _target_skill_arg(payload, request),
        },
        errors=[],
    )


def parse_kt_json_lines(stdout: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            item = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict) and "知识点id" in item:
            rows.append(item)
    return rows


def _predictions_from_kt_rows(
    request: KTPredictRequest,
    rows: list[dict[str, Any]],
) -> list[Prediction]:
    row_by_skill_id = {int(row["知识点id"]): row for row in rows}
    predictions: list[Prediction] = []
    for target in request.targets:
        skill_id = int(target.skill_id)
        row = row_by_skill_id.get(skill_id)
        if row is None:
            continue
        mastery_percent = float(row.get("掌握度") or 0.0)
        mastery_status = str(row.get("掌握情况") or "")
        knowledge_name = str(row.get("知识点") or f"知识点{skill_id}")
        predictions.append(
            Prediction(
                target={
                    "skill_id": skill_id,
                    **({"item_id": int(target.item_id)} if target.item_id is not None else {}),
                },
                probability_correct=max(0.0, min(1.0, mastery_percent / 100.0)),
                observed_correct=target.observed_correct,
                extras={
                    "backend": "kt_cli",
                    "knowledge_point_name": knowledge_name,
                    "mastery_percent": mastery_percent,
                    "mastery_status": mastery_status,
                },
            )
        )
    return predictions


def _missing_prediction_targets(
    request: KTPredictRequest,
    rows: list[dict[str, Any]],
) -> list[int]:
    returned_ids = {int(row["知识点id"]) for row in rows}
    return [
        int(target.skill_id)
        for target in request.targets
        if int(target.skill_id) not in returned_ids
    ]
