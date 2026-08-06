"""Measure the standalone safety-guidance transformation on all GUIDE cases."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings
from app.services.llm_client import LLMClient
from app.services.safety_guidance_skill import SafetyGuidanceSkill
from app.services.safety_pipeline import (
    SafetyPipeline,
    _ALLOWED_CONTENT,
    _FORBIDDEN_CONTENT,
)
from tests.run_safety_evaluation import DATASET_PATH, conversation_context, load_cases


RESULTS_DIR = Path(__file__).with_name("results")


class CountingLLMClient(LLMClient):
    def __init__(self) -> None:
        super().__init__()
        self.model_calls = 0
        self.last_content: Any = None

    async def chat_completion(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.model_calls += 1
        result = await super().chat_completion(*args, **kwargs)
        self.last_content = result.get("content")
        return result


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * quantile) - 1))
    return ordered[index]


async def run_case(
    case: dict[str, str], *, semaphore: asyncio.Semaphore
) -> dict[str, Any]:
    async with semaphore:
        client = CountingLLMClient()
        skill = SafetyGuidanceSkill(llm=client)
        category = case["expected_category"]
        core_topic = SafetyPipeline._infer_core_topic(case["query"], category)
        input_data = {
            "mode": "transform",
            "original_query": case["query"],
            "core_topic": core_topic,
            "safe_learning_goal": f"了解{core_topic}的基本原理、风险后果与安全防护",
            "student_grade": "初中",
            "risk_category": category,
            "intent": "learning",
            "risk_reason": case["rationale"],
            "operational_request": any(
                marker in case["query"]
                for marker in ("如何", "怎么", "怎样", "步骤", "方法", "制作", "获取")
            ),
            "bottom_line_violation": False,
            "conversation_context": conversation_context(case),
            "forbidden_content": list(_FORBIDDEN_CONTENT),
            "allowed_content": list(_ALLOWED_CONTENT),
        }
        started = time.perf_counter()
        try:
            result = await skill.execute(input_data)
            elapsed = round((time.perf_counter() - started) * 1000, 1)
            branches = result.get("subject_options") or []
            valid = bool(
                result.get("status") == "ok"
                and result.get("selection_mode") == "two_stage"
                and 2 <= len(branches) <= 3
                and result.get("safe_query")
                and 2 <= len(result.get("learning_options") or []) <= 3
            )
            return {
                **case,
                "core_topic": core_topic,
                "status": "ok" if valid else "invalid",
                "valid_contract": valid,
                "model_calls": client.model_calls,
                "latency_ms": elapsed,
                "education_domain": result.get("education_domain"),
                "subject_count": len(branches),
                "school_subjects": [item.get("school_subject") for item in branches],
                "subject_labels": [item.get("label") for item in branches],
                "branch_safe_queries": [item.get("safe_query") for item in branches],
                "safe_query": result.get("safe_query"),
                "error": None if valid else "Skill returned an incomplete contract",
            }
        except Exception as exc:
            return {
                **case,
                "core_topic": core_topic,
                "status": "error",
                "valid_contract": False,
                "model_calls": client.model_calls,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "education_domain": None,
                "subject_count": 0,
                "safe_query": None,
                "error": f"{type(exc).__name__}: {exc}",
                "raw_model_content": client.last_content,
                "traceback": traceback.format_exc(),
            }


def build_summary(results: list[dict[str, Any]], started_at: str) -> dict[str, Any]:
    latencies = [float(item["latency_ms"]) for item in results]
    total = len(results)
    valid = sum(bool(item["valid_contract"]) for item in results)
    calls = [int(item["model_calls"]) for item in results]
    return {
        "dataset": str(DATASET_PATH),
        "scope": "expected GUIDE cases; SafetyGuidanceSkill only",
        "model": settings.llm.model_name,
        "started_at": started_at,
        "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "total": total,
        "valid": valid,
        "success_rate": round(valid / total, 4) if total else 0.0,
        "errors": total - valid,
        "status_distribution": dict(Counter(item["status"] for item in results)),
        "average_latency_ms": round(sum(latencies) / total, 1) if total else 0.0,
        "p50_latency_ms": percentile(latencies, 0.50),
        "p95_latency_ms": percentile(latencies, 0.95),
        "max_latency_ms": max(latencies, default=0.0),
        "total_model_calls": sum(calls),
        "average_model_calls": round(sum(calls) / total, 2) if total else 0.0,
        "model_call_distribution": dict(Counter(str(value) for value in calls)),
        "failed_ids": [item["id"] for item in results if not item["valid_contract"]],
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--indices", default="")
    parser.add_argument("--output-prefix", default="safety_guidance_eval_live")
    args = parser.parse_args()

    cases = [case for case in load_cases(DATASET_PATH) if case["expected_branch"] == "GUIDE"]
    if args.indices:
        selected = [int(value.strip()) for value in args.indices.split(",") if value.strip()]
        cases = [cases[index] for index in selected]
    else:
        cases = cases[args.start :]
        if args.limit > 0:
            cases = cases[: args.limit]
    if not cases:
        raise SystemExit("No GUIDE cases selected")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    details_path = RESULTS_DIR / f"{args.output_prefix}.jsonl"
    summary_path = RESULTS_DIR / f"{args.output_prefix}_summary.json"
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    semaphore = asyncio.Semaphore(max(1, args.concurrency))
    print(
        f"Starting {len(cases)} guidance-only cases with model={settings.llm.model_name}, "
        f"concurrency={max(1, args.concurrency)}",
        flush=True,
    )
    tasks = [asyncio.create_task(run_case(case, semaphore=semaphore)) for case in cases]
    results: list[dict[str, Any]] = []
    for completed, task in enumerate(asyncio.as_completed(tasks), start=1):
        results.append(await task)
        if completed % 10 == 0 or completed == len(tasks):
            valid = sum(bool(item["valid_contract"]) for item in results)
            print(f"progress={completed}/{len(tasks)} valid={valid}", flush=True)

    results.sort(key=lambda item: int(item["id"].split("-")[1]))
    details_path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in results),
        encoding="utf-8",
    )
    summary = build_summary(results, started_at)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print(f"details={details_path}", flush=True)
    print(f"summary={summary_path}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
