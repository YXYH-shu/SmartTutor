"""Ranking metrics for temporal validation and test sets."""

from __future__ import annotations

import math
from collections import defaultdict

import torch

from algorithm.graph_recommender.data.graph_builder import GraphData
from algorithm.graph_recommender.data.splits import LinkSplits
from algorithm.graph_recommender.models.hetero_gat import symmetric_logits


def _summarize_ranks(
    ranks: list[int], aucs: list[float], ks: tuple[int, ...] = (5, 10)
) -> dict[str, float]:
    if not ranks:
        return {metric: 0.0 for metric in ("auc", "mrr", *(f"recall@{k}" for k in ks), *(f"ndcg@{k}" for k in ks))}
    metrics = {
        "auc": sum(aucs) / len(aucs),
        "mrr": sum(1 / rank for rank in ranks) / len(ranks),
    }
    for k in ks:
        metrics[f"recall@{k}"] = sum(rank <= k for rank in ranks) / len(ranks)
        metrics[f"ndcg@{k}"] = sum((1 / math.log2(rank + 1)) if rank <= k else 0 for rank in ranks) / len(ranks)
    return metrics


@torch.no_grad()
def evaluate_resources(scorer, embeddings, graph_data: GraphData, splits: LinkSplits) -> dict[str, float]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for learner_id, resource_id in splits.test:
        grouped[learner_id].add(resource_id)
    all_positive = splits.all_positive
    ranks = []
    aucs = []
    resources = embeddings["resource"]
    for learner_id, targets in grouped.items():
        learner_index = graph_data.id_to_index["learner"][learner_id]
        logits = scorer(embeddings["learner"][learner_index].expand_as(resources), resources).view(-1)
        for target in targets:
            allowed = [
                resource_id
                for resource_id in graph_data.node_ids["resource"]
                if (learner_id, resource_id) not in all_positive or resource_id == target
            ]
            target_score = logits[graph_data.id_to_index["resource"][target]]
            negative_values = [
                logits[graph_data.id_to_index["resource"][candidate]]
                for candidate in allowed
                if candidate != target
            ]
            negative_scores = (
                torch.stack(negative_values)
                if negative_values
                else torch.empty(0, device=logits.device)
            )
            rank = 1 + int((negative_scores > target_score).sum().item()) if len(negative_scores) else 1
            auc = (
                float(
                    ((target_score > negative_scores).float().mean()
                    + 0.5 * (target_score == negative_scores).float().mean()).item()
                )
                if len(negative_scores)
                else 1.0
            )
            ranks.append(rank)
            aucs.append(auc)
    return _summarize_ranks(ranks, aucs)


@torch.no_grad()
def evaluate_peers(scorer, embeddings, graph_data: GraphData, splits: LinkSplits) -> dict[str, float]:
    ranks = []
    aucs = []
    positives = splits.all_positive
    all_ids = graph_data.node_ids["learner"]
    for learner_id, target_id in splits.test:
        learner_index = graph_data.id_to_index["learner"][learner_id]
        candidates = [
            candidate
            for candidate in all_ids
            if candidate != learner_id
            and (tuple(sorted((learner_id, candidate))) not in positives or candidate == target_id)
        ]
        indexes = torch.tensor([graph_data.id_to_index["learner"][candidate] for candidate in candidates], device=embeddings["learner"].device)
        scores = symmetric_logits(
            scorer,
            embeddings["learner"][learner_index].expand(len(indexes), -1),
            embeddings["learner"][indexes],
        ).view(-1)
        target_position = candidates.index(target_id)
        target_score = scores[target_position]
        negative_scores = torch.cat((scores[:target_position], scores[target_position + 1 :]))
        rank = 1 + int((negative_scores > target_score).sum().item())
        auc = (
            float(
                ((target_score > negative_scores).float().mean()
                + 0.5 * (target_score == negative_scores).float().mean()).item()
            )
            if len(negative_scores)
            else 1.0
        )
        ranks.append(rank)
        aucs.append(auc)
    return _summarize_ranks(ranks, aucs)
