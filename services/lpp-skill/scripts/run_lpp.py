"""学习路径规划 —— 命令行入口（REKT 后端，最小闭环）。

给定学生 ID 和可选的起始题目 ID，在学生做题序列中定位目标题；若该题预测答对
概率较高，就向后滑动到下一题，直到找到低概率题或序列末题。随后用 DSMOEA 同款的
双策略多目标遗传算法搜索一个尽量短的推荐练习序列。

打分器用的是 `kt-runtime-skill` 里已经训练好的 REKT 模型（不需要重新训练），
数据也直接读 `kt-runtime-skill` 的数据集，不需要做任何格式转换。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

import numpy as np
import torch

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from lpp_runtime.data.rekt_provider import RektHistoryProvider  # noqa: E402
from lpp_runtime.scorers.rekt_scorer import RektScorer  # noqa: E402
from lpp_runtime.search.genetic_algorithm import GeneticAlgorithmBase  # noqa: E402


FIXED_RECOMMENDATION_SIZE = 5
RELATED_QUESTION_LIMIT = 1
QUESTION_TYPE_NAMES = {
    "single_choice": "单选题",
    "fill_blank": "填空题",
    "true_false": "判断题",
}


def parse_cli_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="基于 REKT 的学习路径规划最小闭环")
    parser.add_argument("--student-id", type=str, required=True)
    parser.add_argument(
        "--target-question-id",
        type=int,
        default=None,
        help="从学生序列最后一次出现的该题开始寻找规划目标；不传时从第 length+1 道开始",
    )
    parser.add_argument(
        "--preferred-skill-ids",
        type=str,
        default="",
        help="按优先级排列的 KT 薄弱知识点 ID，逗号分隔；显式题号优先",
    )
    parser.add_argument("--length", type=int, default=10, help="用作历史上下文的交互条数")
    parser.add_argument("--pop-size", type=int, default=50)
    parser.add_argument("--max-gen", type=int, default=100)
    parser.add_argument("--weights", type=str, default="0.9,0.1")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--top-k-knowledge",
        type=int,
        default=5,
        help="从经验矩阵里推荐前 K 个对目标最有用的知识点（默认 5）",
    )
    parser.add_argument(
        "--min-sample",
        type=int,
        default=5,
        help="进入前 K 排行的知识点至少要被采样过多少次（过滤低采样噪声，默认 5）",
    )
    return parser.parse_args(argv)


def dedupe_keep_order(question_ids: list[int]) -> list[int]:
    seen = set()
    deduped = []
    for q in question_ids:
        q = int(q)
        if q in seen:
            continue
        seen.add(q)
        deduped.append(q)
    return deduped


def find_starting_target_index(
    question_ids: list[int], target_question_id: int | None, length: int
) -> int:
    """定位滑窗起点；指定题目重复出现时，取序列中最后一次出现的位置。"""
    if target_question_id is None:
        return min(length, len(question_ids) - 1)
    for index in range(len(question_ids) - 1, -1, -1):
        if int(question_ids[index]) == int(target_question_id):
            return index
    raise ValueError(f"学生做题序列中不存在题目 {target_question_id}")


def choose_starting_target_index(
    *,
    question_ids: list[int],
    target_question_id: int | None,
    preferred_skill_ids: list[int],
    skills_for_question: Callable[[int], list[int]],
    length: int,
) -> tuple[int, str]:
    """Resolve the LPP scan start without changing its downstream scan logic."""
    if target_question_id is not None:
        return (
            find_starting_target_index(
                question_ids,
                target_question_id,
                length,
            ),
            "explicit_question",
        )

    for preferred_skill_id in preferred_skill_ids:
        for index in range(len(question_ids) - 1, -1, -1):
            question_skills = skills_for_question(int(question_ids[index]))
            if int(preferred_skill_id) in {
                int(skill_id) for skill_id in question_skills
            }:
                return index, "kt_weak_skill"

    return (
        find_starting_target_index(question_ids, None, length),
        "default_history_window",
    )


def build_prediction_inputs(
    question_ids: list[int], is_corrects: list[int], target_index: int, length: int, device: torch.device
) -> tuple[list[int], list[int], torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    """为指定目标题构建其前最多 ``length`` 道题的预测上下文。"""
    history_start = max(0, target_index - length)
    hist_q_list = question_ids[history_start:target_index]
    hist_a_list = is_corrects[history_start:target_index]
    target_question = question_ids[target_index]
    target_answer = is_corrects[target_index]

    hist_q = torch.tensor(hist_q_list, dtype=torch.long).reshape(1, len(hist_q_list)).to(device)
    hist_a = torch.tensor(hist_a_list, dtype=torch.long).reshape(1, len(hist_a_list)).to(device)
    # REKT 只读取 next_q 的最后一位；完整的右移序列保持与既有 GA 接口对齐。
    next_q_list = hist_q_list[1:] + [target_question]
    next_a_list = hist_a_list[1:] + [target_answer]
    next_q = torch.tensor(next_q_list, dtype=torch.long).reshape(1, len(next_q_list)).to(device)
    next_a = torch.tensor(next_a_list, dtype=torch.long).reshape(1, len(next_a_list)).to(device)
    return hist_q_list, hist_a_list, hist_q, hist_a, next_q, next_a


def build_question_payload(
    scorer: RektScorer, question_id: int, order: int | None = None
) -> dict[str, object]:
    """构造稳定的题目 JSON，供 Agent 生成学生侧表达。"""
    item = scorer.question_metadata(question_id)
    skills = scorer.skills_of(question_id)
    raw_type = str(item.get("type") or "")
    payload: dict[str, object] = {
        "question_id": int(question_id),
        "question_text": str(item["question_desc"]),
        "question_type": QUESTION_TYPE_NAMES.get(raw_type, "练习题"),
        "question_type_code": raw_type or None,
        "knowledge_points": [
            dict(scorer.knowledge_metadata(skill_id))
            for skill_id in skills
        ],
        "difficulty": float(item["difficulty"]) if item.get("difficulty") is not None else None,
        "grade": item.get("grade"),
        # 当前 REKT 题库未提供单选题选项；保留该字段，让调用方不能误以为选项丢失。
        "options": list(item.get("options") or []),
    }
    if order is not None:
        payload["order"] = order
    return payload


def build_related_questions(
    scorer: RektScorer,
    skill_id: int,
    excluded_question_ids: set[int],
    limit: int = RELATED_QUESTION_LIMIT,
) -> list[dict[str, object]]:
    """返回同一知识点下的其他题目，作为延伸练习而非主推荐题。"""
    related_questions = []
    for question_id in sorted(scorer.questions_of_skill(skill_id)):
        if question_id in excluded_question_ids:
            continue
        related_questions.append(build_question_payload(scorer, question_id))
        if len(related_questions) >= limit:
            break
    return related_questions


def build_purpose_and_effect(
    order: int,
    knowledge_points: list[dict[str, object]],
    target: dict[str, object],
) -> str:
    """为展示层提供不涉及算法细节的、顺序相关的练习目的。"""
    knowledge_names = "、".join(
        str(item["knowledge_point_name"]) for item in knowledge_points
    ) or "相关知识点"
    target_names = "、".join(
        str(item["knowledge_point_name"])
        for item in target.get("knowledge_points", [])
    ) or "目标题相关能力"
    if order == 1:
        return f"优先建立“{knowledge_names}”的基础理解，为后续练习做准备。"
    if order == FIXED_RECOMMENDATION_SIZE:
        return f"完成“{knowledge_names}”的巩固练习，并衔接“{target_names}”相关能力。"
    return f"在前序练习基础上巩固“{knowledge_names}”，为后续练习逐步建立条件。"


def build_plan_items(
    scorer: RektScorer,
    recommended_questions: list[dict[str, object]],
    target: dict[str, object],
) -> list[dict[str, object]]:
    """将 5 道主推荐题扩展为 Agent 可直接消费的详细规划信息。"""
    plan_items = []
    for question in recommended_questions:
        # 关联题只排除当前题和目标题。REKT 题库中一个知识点通常只有 3 道题，
        # 因此允许关联到同一组主推荐中的另一道题，避免资源列表全为空。
        excluded_question_ids = {
            int(question["question_id"]),
            int(target["question_id"]),
        }
        knowledge_points = list(question["knowledge_points"])
        knowledge_sequences = []
        related_questions = []
        seen_related_question_ids = set()
        for knowledge_point in knowledge_points:
            skill_id = int(knowledge_point["knowledge_point_id"])
            skill_related_questions = build_related_questions(
                scorer, skill_id, excluded_question_ids
            )
            for related_question in skill_related_questions:
                question_id = int(related_question["question_id"])
                if question_id not in seen_related_question_ids:
                    seen_related_question_ids.add(question_id)
                    related_questions.append(related_question)
            knowledge_sequences.append(
                {
                    "knowledge_point_id": skill_id,
                    "knowledge_sequence": scorer.knowledge_sequence(skill_id),
                }
            )

        order = int(question["order"])
        plan_items.append(
            {
                "priority": f"P{order}",
                "question_id": int(question["question_id"]),
                "purpose_and_effect": build_purpose_and_effect(order, knowledge_points, target),
                "knowledge_sequences": knowledge_sequences,
                "related_questions": related_questions,
            }
        )
    return plan_items


def build_response(
    *,
    status: str,
    student_id: str,
    message: str,
    recommendation: dict[str, object] | None = None,
    target: dict[str, object] | None = None,
    plan_items: list[dict[str, object]] | None = None,
    data_sources: dict[str, object] | None = None,
    diagnostics: dict[str, object] | None = None,
) -> dict[str, object]:
    """所有正常与异常路径共用的命令行 JSON 契约。"""
    return {
        "status": status,
        "task": "learning_path_planning",
        "student_id": str(student_id),
        "message": message,
        "target": target,
        "recommendation": recommendation or {"count": 0, "questions": []},
        "plan_items": plan_items or [],
        "data_sources": data_sources or {},
        "diagnostics": diagnostics or {},
    }


def collect_positive_ace_skills(
    ace_col: np.ndarray,
    weight_col: np.ndarray,
    target_sid: int,
    min_sample: int,
) -> list[tuple[int, float, int]]:
    """按给定采样门槛收集"正 ACE"的知识点，按 ACE 降序返回。"""
    rows = []
    for src_sid in range(len(ace_col)):
        if src_sid == target_sid:
            continue
        if weight_col[src_sid] < min_sample:
            continue
        if ace_col[src_sid] <= 0:
            continue
        rows.append((src_sid, float(ace_col[src_sid]), int(weight_col[src_sid])))
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows


def build_top_k_knowledge(
    ace_col: np.ndarray,
    weight_col: np.ndarray,
    target_sid: int,
    top_k: int,
    min_sample: int,
) -> tuple[list[tuple[int, float, int]], bool]:
    """从经验矩阵里挑前 K 个知识点，不足时逐步放宽采样门槛补齐。"""
    thresholds = sorted({min_sample, 3, 1}, reverse=True)
    thresholds = [t for t in thresholds if t <= min_sample] or [1]

    results = []
    used_relaxed = False
    seen = set()
    for th in thresholds:
        if len(results) >= top_k:
            break
        for sid, ace, wt in collect_positive_ace_skills(ace_col, weight_col, target_sid, th):
            if sid in seen:
                continue
            seen.add(sid)
            results.append((sid, ace, wt))
            if wt < min_sample:
                used_relaxed = True
            if len(results) >= top_k:
                break
    return results[:top_k], used_relaxed


def fill_recommendation_to_fixed_size(
    scorer: RektScorer,
    original_questions: list[int],
    hist_q_list: list[int],
    target_question: int,
    target_skills: list[int],
    top_k_knowledge: list[tuple[int, float, int]],
    fallback_candidates: list[int],
    fixed_size: int = FIXED_RECOMMENDATION_SIZE,
) -> tuple[list[int], list[int]]:
    """把 GA 搜出的短序列补齐到固定题数，同时尽量不破坏原始顺序。

    补齐优先级：
    1. 保留 GA 原始顺序并去重。
    2. 从目标题对应知识点的题目里补。
    3. 从 ACE 排行靠前知识点的题目里补。
    4. 从更宽的候选池兜底。
    """
    history_questions = {int(q) for q in hist_q_list}
    filled = [q for q in dedupe_keep_order(original_questions) if q != target_question]
    original_deduped = list(filled)
    seen = set(filled)

    def append_from_pool(pool: list[int], *, allow_history: bool) -> None:
        for q in pool:
            q = int(q)
            if len(filled) >= fixed_size:
                return
            if q == target_question or q in seen:
                continue
            if not allow_history and q in history_questions:
                continue
            if not scorer.skills_of(q):
                continue
            seen.add(q)
            filled.append(q)

    target_skill_questions = []
    for sid in target_skills:
        target_skill_questions.extend(scorer.questions_of_skill(sid))

    ace_skill_questions = []
    for sid, _, _ in top_k_knowledge:
        ace_skill_questions.extend(scorer.questions_of_skill(sid))

    append_from_pool(target_skill_questions, allow_history=False)
    append_from_pool(ace_skill_questions, allow_history=False)
    append_from_pool(fallback_candidates, allow_history=False)

    if len(filled) < fixed_size:
        append_from_pool(target_skill_questions, allow_history=True)
        append_from_pool(ace_skill_questions, allow_history=True)
        append_from_pool(fallback_candidates, allow_history=True)

    if len(filled) < fixed_size:
        raise RuntimeError(f"可用题目不足，无法生成固定 {fixed_size} 道不同练习题")

    return filled[:fixed_size], original_deduped


def run_planning(args: argparse.Namespace) -> dict[str, object]:
    if args.seed is not None:
        import random

        random.seed(args.seed)
        np.random.seed(args.seed)
        torch.manual_seed(args.seed)

    weights = tuple(float(x) for x in args.weights.split(","))

    scorer = RektScorer()
    history_provider = RektHistoryProvider(scorer)
    device = scorer.device

    history = history_provider.get_history(args.student_id)
    length = args.length
    if not history.question_ids:
        raise ValueError(f"学生 {args.student_id} 没有可用的做题记录")

    preferred_skill_ids = [
        int(value.strip())
        for value in str(args.preferred_skill_ids or "").split(",")
        if value.strip()
    ]
    initial_target_index, initial_target_source = choose_starting_target_index(
        question_ids=history.question_ids,
        target_question_id=args.target_question_id,
        preferred_skill_ids=preferred_skill_ids,
        skills_for_question=scorer.skills_of,
        length=length,
    )
    target_index = initial_target_index
    scanned_target_indices = []
    forced_last_target = False

    while True:
        (
            hist_q_list,
            hist_a_list,
            hist_q,
            hist_a,
            next_q,
            next_a,
        ) = build_prediction_inputs(
            history.question_ids, history.is_corrects, target_index, length, device
        )
        target_question = history.question_ids[target_index]
        with torch.inference_mode():
            pred = scorer.forward_batch(hist_q, hist_a, next_q)
        base = float(pred[:, -1].item())
        scanned_target_indices.append(target_index)

        is_last_question = target_index == len(history.question_ids) - 1
        if base < 0.5 or is_last_question:
            forced_last_target = is_last_question and base >= 0.5
            break
        target_index += 1

    target_payload = build_question_payload(scorer, target_question)
    wrong_count = sum(1 for answer in hist_a_list if answer == 0)

    target_skills = scorer.skills_of(target_question)
    if not target_skills:
        raise ValueError(f"题目 {target_question} 在 REKT 数据里没有对应的知识点映射")

    # 只保留能查到知识点的有效题目 id（全量 range 里可能含不存在的 id，
    # 比如 REKT 题目是 1..1002，但 question_universe_size=1003 含 id 0）。
    question_universe = [
        q for q in range(scorer.question_universe_size) if scorer.skills_of(q)
    ]
    candidate_pool_all = question_universe
    candidate_pool_default = question_universe

    # 探索策略：排除"历史 + 目标题目"涉及技能对应的题目
    touched_skills = set(target_skills)
    for q in hist_q_list:
        touched_skills.update(scorer.skills_of(q))
    touched_questions = set()
    for s in touched_skills:
        touched_questions.update(scorer.questions_of_skill(s))
    candidate_pool_untried_skill = [q for q in question_universe if q not in touched_questions]

    # 利用策略：历史错题 + 目标题目对应技能的题目
    wrong_questions = [q for q, a in zip(hist_q_list, hist_a_list) if a == 0] + [target_question]
    wrong_skills = set()
    for q in wrong_questions:
        wrong_skills.update(scorer.skills_of(q))
    candidate_pool_wrong_skill = []
    for s in wrong_skills:
        candidate_pool_wrong_skill.extend(scorer.questions_of_skill(s))

    # 技能相关策略：目标题目对应技能的题目
    candidate_pool_target_skill = []
    for s in target_skills:
        candidate_pool_target_skill.extend(scorer.questions_of_skill(s))

    skill_num = scorer.data.skl_num
    e_ICEf = np.zeros((skill_num, skill_num), dtype=np.float64)
    e_weightf = np.zeros((skill_num, skill_num), dtype=np.int64)
    e_ACEf = np.zeros((skill_num, skill_num), dtype=np.float64)

    ga = GeneticAlgorithmBase(
        scorer=scorer,
        e_ICEf=e_ICEf,
        e_ACEf=e_ACEf,
        e_weightf=e_weightf,
        hist_q=hist_q,
        hist_a=hist_a,
        next_q=next_q,
        next_a=next_a,
        hist_q_old=hist_q,
        hist_a_old=hist_a,
        next_q_old=next_q,
        next_a_old=next_a,
        base=base,
        target_question=target_question,
        target_skills=target_skills,
        candidate_pool_all=candidate_pool_all,
        candidate_pool_default=candidate_pool_default,
        candidate_pool_untried_skill=candidate_pool_untried_skill,
        candidate_pool_wrong_skill=candidate_pool_wrong_skill,
        candidate_pool_target_skill=candidate_pool_target_skill,
        skill_num=skill_num,
        matrix=True,
    )

    result = ga.run0707(pop_size=args.pop_size, max_gen=args.max_gen, weights=weights)

    e_ACEf = result["e_ACEf"]
    e_weightf = result["e_weightf"]
    target_sid = target_skills[0]
    ace_col = e_ACEf[:, target_sid]
    weight_col = e_weightf[:, target_sid]

    top_k, _ = build_top_k_knowledge(
        ace_col=ace_col,
        weight_col=weight_col,
        target_sid=target_sid,
        top_k=args.top_k_knowledge,
        min_sample=args.min_sample,
    )
    ga_questions = result["recommended_questions"]
    recommended_questions, _ = fill_recommendation_to_fixed_size(
        scorer=scorer,
        original_questions=ga_questions,
        hist_q_list=hist_q_list,
        target_question=target_question,
        target_skills=target_skills,
        top_k_knowledge=top_k,
        fallback_candidates=candidate_pool_default,
        fixed_size=FIXED_RECOMMENDATION_SIZE,
    )
    recommended_question_payloads = [
        build_question_payload(scorer, question_id, rank)
        for rank, question_id in enumerate(recommended_questions, 1)
    ]
    target_with_probabilities = {
        **target_payload,
        "baseline_correctness_probability": base,
        "planned_correctness_probability": float(result["final_score"]),
        "correctness_probability_gain": float(result["effect_gain"]),
    }
    return build_response(
        status="ok",
        student_id=args.student_id,
        message="recommendations_ready",
        target=target_with_probabilities,
        recommendation={
            "count": FIXED_RECOMMENDATION_SIZE,
            "questions": recommended_question_payloads,
        },
        plan_items=build_plan_items(scorer, recommended_question_payloads, target_with_probabilities),
        data_sources={
            "knowledge_sequence": "knowledges.json (grade_order + topic_id + seq)",
            "related_questions": "exercise_info.json (same knowledge_point_id)",
        },
        diagnostics={
            "history_window_size": length,
            "wrong_answer_count": wrong_count,
            "initial_target_source": initial_target_source,
            "initial_target_index": initial_target_index,
            "selected_target_index": target_index,
            "scanned_target_count": len(scanned_target_indices),
            "forced_last_target": forced_last_target,
            "algorithm": "DSMOEA",
        },
    )


def main(argv=None) -> None:
    args = parse_cli_args(argv)
    try:
        response = run_planning(args)
    except Exception as exc:
        response = build_response(
            status="error",
            student_id=args.student_id,
            message=str(exc),
        )

    print(json.dumps(response, ensure_ascii=False, indent=2))
    if response["status"] != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
