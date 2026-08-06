"""Frozen-encoder task-head training for resources and peers."""

from __future__ import annotations

import random
from dataclasses import dataclass

import torch
import torch.nn.functional as F

from algorithm.graph_recommender.data.graph_builder import GraphData
from algorithm.graph_recommender.data.splits import LinkSplits
from algorithm.graph_recommender.models.hetero_gat import MLPScorer, symmetric_logits


@dataclass(frozen=True)
class TaskTrainingConfig:
    epochs: int = 100
    learning_rate: float = 1e-3
    weight_decay: float = 0.0
    negatives_per_positive: int = 5
    seed: int = 42
    device: str = "auto"


def _device(value: str) -> torch.device:
    if value == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(value)


@torch.no_grad()
def encode_graph(encoder, graph, device: torch.device) -> dict[str, torch.Tensor]:
    encoder = encoder.to(device).eval()
    output = encoder(graph.to(device))
    return {node_type: values.detach() for node_type, values in output.items()}


def train_resource_scorer(
    encoder,
    graph,
    graph_data: GraphData,
    splits: LinkSplits,
    config: TaskTrainingConfig,
) -> MLPScorer:
    if not splits.train:
        raise ValueError("resource training needs at least one training interaction")
    device = _device(config.device)
    embeddings = encode_graph(encoder, graph, device)
    learners = embeddings["learner"]
    resources = embeddings["resource"]
    scorer = MLPScorer(learners.size(-1)).to(device)
    optimizer = torch.optim.Adam(scorer.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
    rng = random.Random(config.seed)
    all_resource_ids = list(graph_data.node_ids["resource"])
    known_by_learner: dict[str, set[str]] = {}
    for learner_id, resource_id in splits.all_positive:
        known_by_learner.setdefault(learner_id, set()).add(resource_id)
    train_pairs = sorted(splits.train)
    for _ in range(config.epochs):
        rng.shuffle(train_pairs)
        scorer.train()
        for learner_id, positive_id in train_pairs:
            negative_pool = [
                resource_id
                for resource_id in all_resource_ids
                if resource_id not in known_by_learner.get(learner_id, set())
            ]
            if not negative_pool:
                continue
            negative_ids = [rng.choice(negative_pool) for _ in range(config.negatives_per_positive)]
            learner_index = graph_data.id_to_index["learner"][learner_id]
            positive_index = graph_data.id_to_index["resource"][positive_id]
            negative_indices = [graph_data.id_to_index["resource"][item] for item in negative_ids]
            source = learners[learner_index].unsqueeze(0).expand(len(negative_indices), -1)
            positive = resources[positive_index].unsqueeze(0).expand(len(negative_indices), -1)
            negative = resources[negative_indices]
            loss = -F.logsigmoid(scorer(source, positive) - scorer(source, negative)).mean()
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
    return scorer.eval()


def _peer_negative_pairs(
    learner_ids: list[str],
    positives: set[tuple[str, str]],
    count: int,
    rng: random.Random,
) -> list[tuple[str, str]]:
    possible = [
        (left, right)
        for index, left in enumerate(learner_ids)
        for right in learner_ids[index + 1 :]
        if (left, right) not in positives
    ]
    if not possible:
        return []
    return [rng.choice(possible) for _ in range(count)]


def train_peer_scorer(
    encoder,
    graph,
    graph_data: GraphData,
    splits: LinkSplits,
    config: TaskTrainingConfig,
) -> MLPScorer:
    if not splits.train:
        raise ValueError("peer training needs at least one training relation")
    device = _device(config.device)
    embeddings = encode_graph(encoder, graph, device)
    learners = embeddings["learner"]
    scorer = MLPScorer(learners.size(-1)).to(device)
    optimizer = torch.optim.Adam(scorer.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
    rng = random.Random(config.seed)
    learner_ids = graph_data.node_ids["learner"]
    positive_pairs = splits.all_positive
    for _ in range(config.epochs):
        positives = sorted(splits.train)
        rng.shuffle(positives)
        negatives = _peer_negative_pairs(
            learner_ids, positive_pairs, len(positives) * config.negatives_per_positive, rng
        )
        pairs = positives + negatives
        labels = [1.0] * len(positives) + [0.0] * len(negatives)
        if not pairs:
            break
        left = torch.tensor([graph_data.id_to_index["learner"][pair[0]] for pair in pairs], device=device)
        right = torch.tensor([graph_data.id_to_index["learner"][pair[1]] for pair in pairs], device=device)
        logits = symmetric_logits(scorer, learners[left], learners[right]).view(-1)
        loss = F.binary_cross_entropy_with_logits(logits, torch.tensor(labels, device=device))
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
    return scorer.eval()
