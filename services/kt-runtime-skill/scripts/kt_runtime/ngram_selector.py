from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

QUERY_CONTROL_TERMS = {
    "学习",
    "最近",
    "学生",
    "当前",
    "现在",
    "分析",
    "学情",
    "情况",
    "知识",
    "知识点",
    "内容",
    "相关",
    "问题",
    "解释",
    "理解",
    "描述",
    "判断",
    "掌握",
    "主题",
    "上下文",
    "请帮",
    "帮我",
}


def _normalize_text(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[\s\r\n\t]+", " ", text)
    return text


def _remove_control_terms(text: str) -> str:
    cleaned = text or ""
    for term in QUERY_CONTROL_TERMS:
        cleaned = cleaned.replace(term, " ")
    return cleaned


def _char_stream(text: str) -> str:
    chars = []
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff" or ch.isalnum():
            chars.append(ch)
    return "".join(chars)


def build_ngram_counter(text: str, min_n: int = 1, max_n: int = 4) -> Counter[str]:
    normalized = _normalize_text(_remove_control_terms(text))
    compact = _char_stream(normalized)
    counter: Counter[str] = Counter()
    if compact:
        for n in range(min_n, max_n + 1):
            if len(compact) < n:
                continue
            for index in range(len(compact) - n + 1):
                ngram = compact[index : index + n]
                if _is_useful_ngram(ngram):
                    counter[ngram] += 1
    for token in normalized.split(" "):
        token = _char_stream(token.strip())
        if token and len(token) <= max_n and _is_useful_ngram(token):
            counter[token] += 1
    return counter


def _is_useful_ngram(ngram: str) -> bool:
    if not ngram:
        return False
    if ngram in QUERY_CONTROL_TERMS:
        return False
    function_chars = set("的是在了和与或我你他她它请帮吗么")
    if len(ngram) == 1:
        return False
    return not any(ch in function_chars for ch in ngram)


def _query_terms(text: str) -> list[str]:
    normalized = _normalize_text(_remove_control_terms(text))
    separators = set("的是在了和与或我你他她它请帮吗么，。！？；：、,.!?;:()（）[]【】")
    chars = []
    for ch in normalized:
        if ch in separators or ch.isspace():
            chars.append(" ")
        else:
            chars.append(ch)
    terms = []
    seen = set()
    for raw in "".join(chars).split():
        term = _char_stream(raw)
        if not term or term in QUERY_CONTROL_TERMS or term in seen:
            continue
        terms.append(term)
        seen.add(term)
    return terms


def overlap_score(query_counter: Counter[str], candidate_counter: Counter[str]) -> float:
    if not query_counter or not candidate_counter:
        return 0.0
    shared = 0.0
    for key, value in query_counter.items():
        shared += min(value, candidate_counter.get(key, 0))
    query_norm = math.sqrt(sum(value * value for value in query_counter.values()))
    cand_norm = math.sqrt(sum(value * value for value in candidate_counter.values()))
    if query_norm == 0.0 or cand_norm == 0.0:
        return 0.0
    return shared / (query_norm * cand_norm)


def weighted_overlap_score(
    query_counter: Counter[str],
    candidate_counter: Counter[str],
    term_weights: dict[str, float],
) -> float:
    if not query_counter or not candidate_counter:
        return 0.0
    shared = 0.0
    for key, value in query_counter.items():
        weight = term_weights.get(key, 1.0)
        shared += min(value, candidate_counter.get(key, 0)) * weight * weight
    query_norm = math.sqrt(
        sum((value * term_weights.get(key, 1.0)) ** 2 for key, value in query_counter.items())
    )
    cand_norm = math.sqrt(
        sum((value * term_weights.get(key, 1.0)) ** 2 for key, value in candidate_counter.items())
    )
    if query_norm == 0.0 or cand_norm == 0.0:
        return 0.0
    return shared / (query_norm * cand_norm)


def _candidate_text(item: dict[str, Any]) -> str:
    return str(item.get("knowledge_point_description") or "")


def _candidate_counters(candidates: list[dict[str, Any]]) -> dict[int, Counter[str]]:
    return {index: build_ngram_counter(_candidate_text(item)) for index, item in enumerate(candidates)}


def _recent_interaction_text(recent_interactions: list[dict[str, Any]]) -> str:
    parts = []
    for item in recent_interactions:
        if not isinstance(item, dict):
            continue
        description = str(item.get("knowledge_point_description") or "").strip()
        name = str(item.get("knowledge_point_name") or "").strip()
        if description:
            parts.append(description)
        elif name:
            parts.append(name)
    return " ".join(parts)


def _term_weights(candidate_counters: dict[int, Counter[str]]) -> dict[str, float]:
    total_docs = max(1, len(candidate_counters))
    document_frequency: Counter[str] = Counter()
    for counter in candidate_counters.values():
        document_frequency.update(counter.keys())
    weights = {}
    for term, frequency in document_frequency.items():
        if len(term) == 1 and frequency / total_docs > 0.085:
            weights[term] = 0.0
        else:
            weights[term] = math.log((1.0 + total_docs) / (1.0 + frequency)) + 1.0
    return weights


def _query_term_weights(candidates: list[dict[str, Any]], query_terms: list[str]) -> dict[str, float]:
    total_docs = max(1, len(candidates))
    weights = {}
    for term in query_terms:
        frequency = sum(1 for item in candidates if term in _candidate_text(item))
        weights[term] = math.log((1.0 + total_docs) / (1.0 + frequency)) + 1.0
    return weights


def _query_term_coverage(
    candidate_text: str,
    query_terms: list[str],
    query_term_weights: dict[str, float],
) -> tuple[float, list[str]]:
    if not query_terms:
        return 0.0, []
    total = sum(query_term_weights.get(term, 1.0) for term in query_terms)
    if total <= 0:
        return 0.0, []
    matched = [term for term in query_terms if term in candidate_text]
    matched_weight = sum(query_term_weights.get(term, 1.0) for term in matched)
    return matched_weight / total, matched


def _matched_terms(
    query_counter: Counter[str],
    candidate_counter: Counter[str],
    term_weights: dict[str, float],
) -> list[str]:
    matched = []
    scored_terms = []
    for term, count in query_counter.items():
        if candidate_counter.get(term, 0) <= 0:
            continue
        weight = term_weights.get(term, 1.0)
        scored_terms.append((count * weight, len(term), term))
    scored_terms.sort(reverse=True)
    for _score, _length, term in scored_terms[:4]:
        matched.append(term)
    return matched


def select_relevant_knowledge_points(
    candidates: list[dict[str, Any]],
    *,
    initial_query: str,
    history_context: str,
    recent_interactions: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    top_k = max(1, int(top_k))
    primary_text = " ".join(
        part for part in [history_context or "", initial_query or ""] if part
    ).strip()
    selector_text = primary_text
    if not selector_text:
        selector_text = _recent_interaction_text(recent_interactions)

    primary_counter = build_ngram_counter(selector_text)
    query_terms = _query_terms(selector_text)
    candidate_counters = _candidate_counters(candidates)
    term_weights = _term_weights(candidate_counters)
    query_term_weights = _query_term_weights(candidates, query_terms)

    scored = []
    for index, item in enumerate(candidates):
        candidate_counter = candidate_counters[index]
        ngram_score = weighted_overlap_score(primary_counter, candidate_counter, term_weights)
        coverage_score, covered_terms = _query_term_coverage(
            _candidate_text(item),
            query_terms,
            query_term_weights,
        )
        matched_terms = covered_terms or _matched_terms(primary_counter, candidate_counter, term_weights)
        selection_score = (ngram_score * 0.65) + (coverage_score * 0.35)
        scored.append(
            {
                **item,
                "ngram_score": float(ngram_score),
                "query_term_coverage": float(coverage_score),
                "primary_score": float(selection_score),
                "selection_score": float(selection_score),
                "matched_terms": matched_terms,
                "relation_to_query": "直接相关" if selection_score > 0 else "后续延展",
            }
        )

    scored.sort(
        key=lambda item: (
            -float(item["selection_score"]),
            int(item.get("skill_id", 0)),
        )
    )
    return [{**item, "selection_bucket": "ngram"} for item in scored[:top_k]]
