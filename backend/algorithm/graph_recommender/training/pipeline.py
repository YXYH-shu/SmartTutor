"""End-to-end offline training against the current application database."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import torch

from algorithm.graph_recommender.data.graph_builder import GraphBuilder
from algorithm.graph_recommender.data.repository import GraphRepository
from algorithm.graph_recommender.data.splits import split_peer_relations, split_resource_interactions
from algorithm.graph_recommender.features.embedding import EmbeddingProvider, EmbeddingResolver
from algorithm.graph_recommender.models.checkpoints import GraphModelConfig, save_checkpoints
from algorithm.graph_recommender.models.hetero_gat import MLPScorer

from .evaluate import evaluate_peers, evaluate_resources
from .pretrain import PretrainingConfig, train_encoder
from .tasks import TaskTrainingConfig, encode_graph, train_peer_scorer, train_resource_scorer


@dataclass(frozen=True)
class TrainingConfig:
    checkpoint_dir: str | Path
    model_config: GraphModelConfig
    pretraining: PretrainingConfig = field(default_factory=PretrainingConfig)
    tasks: TaskTrainingConfig = field(default_factory=TaskTrainingConfig)


def _device(value: str) -> torch.device:
    if value == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(value)


def _require_ranking_nodes(rows) -> None:
    if not rows.learners:
        raise ValueError("graph recommender needs at least one learner node")
    if not rows.resources:
        raise ValueError("graph recommender needs at least one resource node")


async def train_from_repository(
    repository: GraphRepository,
    embedding_provider: EmbeddingProvider,
    config: TrainingConfig,
) -> dict[str, object]:
    rows = await repository.load_rows()
    _require_ranking_nodes(rows)
    embeddings = await EmbeddingResolver(repository, embedding_provider).resolve(rows)
    resource_splits = split_resource_interactions(rows.resource_interactions)
    peer_splits = split_peer_relations(rows.partner_relations)
    if not resource_splits.train and not peer_splits.train:
        raise ValueError("no trainable resource or peer relations")
    graph_data = GraphBuilder().build(
        rows,
        embeddings,
        excluded_resource_edges=resource_splits.validation | resource_splits.test,
        excluded_partner_edges=peer_splits.validation | peer_splits.test,
    )
    graph = graph_data.to_heterodata()
    encoder = train_encoder(graph, config.pretraining)
    device = _device(config.tasks.device)
    resource_trained = bool(resource_splits.train)
    peer_trained = bool(peer_splits.train)
    resource_scorer = (
        train_resource_scorer(encoder, graph, graph_data, resource_splits, config.tasks)
        if resource_trained
        else MLPScorer(encoder.output_dim).to(device).eval()
    )
    peer_scorer = (
        train_peer_scorer(encoder, graph, graph_data, peer_splits, config.tasks)
        if peer_trained
        else MLPScorer(encoder.output_dim).to(device).eval()
    )
    encoded = encode_graph(encoder, graph, device)
    resource_metrics = (
        evaluate_resources(resource_scorer, encoded, graph_data, resource_splits)
        if resource_trained
        else None
    )
    peer_metrics = (
        evaluate_peers(peer_scorer, encoded, graph_data, peer_splits)
        if peer_trained
        else None
    )
    statistics: dict[str, object] = {
        "resource_train_pairs": len(resource_splits.train),
        "peer_train_pairs": len(peer_splits.train),
        "resource_test": resource_metrics,
        "peer_test": peer_metrics,
    }
    save_checkpoints(
        config.checkpoint_dir,
        encoder=encoder,
        resource_scorer=resource_scorer,
        peer_scorer=peer_scorer,
        model_config=config.model_config,
    )
    return statistics
