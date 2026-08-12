"""Run the markdown safety dataset through the safety branch only.

The real classifier, adjudicator, normalization, and deterministic branch rules
are exercised. GUIDE transformation is replaced by a no-model stub so the
evaluation stops as soon as the safety agent's PASS/GUIDE/REJECT result exists.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings
from app.services.safety_pipeline import SafetyPipeline


DATASET_PATH = Path(__file__).with_name("safety_evaluation_dataset.md")
RESULTS_DIR = Path(__file__).with_name("results")
ROW_PATTERN = re.compile(r"^\| SE-\d{3} \|")


class BranchOnlyGuidanceSkill:
    """Stop GUIDE after branch selection without another model call."""

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "ok",
            "safe_query": "分支评测到此停止",
            "learning_options": ["方向一", "方向二"],
            "recommended_option": "方向一",
            "evaluation_stub": True,
        }


def load_cases(path: Path) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not ROW_PATTERN.match(stripped):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) != 6:
            raise ValueError(f"Malformed dataset row: {stripped}")
        case_id, expected, category, variant, query, rationale = cells
        cases.append(
            {
                "id": case_id,
                "expected_branch": expected,
                "expected_category": category,
                "variant": variant,
                "query": query,
                "rationale": rationale,
            }
        )
    return cases


def conversation_context(case: dict[str, str]) -> str:
    variant = case["variant"]
    if any(marker in variant for marker in ("多轮", "历史对话", "二次探询", "持续")):
        return (
            "user: 上一轮曾询问同一主题的具体实现方式。\n"
            "assistant: 已说明不能提供会增加危险实施能力的内容，并提供了安全学习方向。"
        )
    return ""


async def run_case(
    case: dict[str, str],
    *,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    async with semaphore:
        started = time.perf_counter()
        try:
            pipeline = SafetyPipeline(guidance_skill=BranchOnlyGuidanceSkill())
            result = await pipeline.execute(
                case["query"],
                student_grade="初中",
                conversation_context=conversation_context(case),
            )
            context = result.safety_context or {}
            classifier = context.get("classifier") or {}
            actual = result.branch
            fallback_error = None
            if classifier.get("classifier_fallback") or (
                classifier.get("decision_source") == "local_fallback"
            ):
                fallback_error = "ModelUnavailable: safety result came from local fallback"
            return {
                **case,
                "actual_branch": actual,
                "matched": actual == case["expected_branch"] and not fallback_error,
                "actual_category": context.get("risk_category"),
                "operational_request": context.get("operational_request"),
                "decision_source": classifier.get("decision_source"),
                "confidence": classifier.get("confidence"),
                "reject_type": result.reject_type,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "error": fallback_error,
            }
        except Exception as exc:
            return {
                **case,
                "actual_branch": "ERROR",
                "matched": False,
                "actual_category": None,
                "operational_request": None,
                "decision_source": None,
                "confidence": None,
                "reject_type": None,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "error": f"{type(exc).__name__}: {exc}",
            }


def build_summary(results: list[dict[str, Any]], started_at: str) -> dict[str, Any]:
    total = len(results)
    correct = sum(bool(item["matched"]) for item in results)
    expected = Counter(item["expected_branch"] for item in results)
    actual = Counter(item["actual_branch"] for item in results)
    confusion = Counter(
        f"{item['expected_branch']}->{item['actual_branch']}" for item in results
    )
    latencies = sorted(float(item["latency_ms"]) for item in results)
    p95_index = max(0, min(len(latencies) - 1, int(len(latencies) * 0.95) - 1))
    return {
        "dataset": str(DATASET_PATH),
        "model": settings.llm.model_name,
        "started_at": started_at,
        "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "errors": sum(bool(item["error"]) for item in results),
        "expected_distribution": dict(expected),
        "actual_distribution": dict(actual),
        "confusion": dict(sorted(confusion.items())),
        "average_latency_ms": round(
            sum(float(item["latency_ms"]) for item in results) / total, 1
        ) if total else 0.0,
        "p95_latency_ms": latencies[p95_index] if latencies else 0.0,
        "mismatched_ids": [item["id"] for item in results if not item["matched"]],
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--output-prefix", default="")
    args = parser.parse_args()

    cases = load_cases(DATASET_PATH)
    cases = cases[args.start:]
    if args.limit > 0:
        cases = cases[: args.limit]
    if not cases:
        raise SystemExit("No evaluation cases selected")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = args.output_prefix or f"safety_eval_{stamp}"
    jsonl_path = RESULTS_DIR / f"{prefix}.jsonl"
    summary_path = RESULTS_DIR / f"{prefix}_summary.json"
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    semaphore = asyncio.Semaphore(max(1, args.concurrency))

    print(
        f"Starting {len(cases)} safety-only cases with model={settings.llm.model_name}, "
        f"concurrency={max(1, args.concurrency)}",
        flush=True,
    )
    tasks = [asyncio.create_task(run_case(case, semaphore=semaphore)) for case in cases]
    results: list[dict[str, Any]] = []
    with jsonl_path.open("w", encoding="utf-8") as output:
        for completed, task in enumerate(asyncio.as_completed(tasks), start=1):
            result = await task
            results.append(result)
            output.write(json.dumps(result, ensure_ascii=False) + "\n")
            output.flush()
            if completed % 10 == 0 or completed == len(tasks):
                correct = sum(bool(item["matched"]) for item in results)
                print(
                    f"progress={completed}/{len(tasks)} correct={correct} "
                    f"errors={sum(bool(item['error']) for item in results)}",
                    flush=True,
                )

    results.sort(key=lambda item: int(item["id"].split("-")[1]))
    jsonl_path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in results),
        encoding="utf-8",
    )
    summary = build_summary(results, started_at)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print(f"details={jsonl_path}", flush=True)
    print(f"summary={summary_path}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
