"""Contrastive pretraining for the shared graph encoder."""

from __future__ import annotations

import copy
from dataclasses import dataclass

import torch
import torch.nn.functional as F

from algorithm.graph_recommender.models.hetero_gat import HeteroGATEncoder, PretrainingModel


@dataclass(frozen=True)
class PretrainingConfig:
    epochs: int = 100
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4
    hidden_dim: int = 64
    output_dim: int = 64
    heads: int = 2
    num_layers: int = 2
    dropout: float = 0.2
    edge_dropout: float = 0.1
    feature_dropout: float = 0.1
    temperature: float = 0.2
    patience: int = 20
    interest_slots: int = 4
    interest_iterations: int = 3
    device: str = "auto"


def _device(value: str) -> torch.device:
    if value == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(value)


def _contrastive(first: torch.Tensor, second: torch.Tensor, temperature: float) -> torch.Tensor:
    if first.size(0) == 0:
        return first.sum() * 0
    labels = torch.arange(first.size(0), device=first.device)
    logits = F.normalize(first, dim=-1) @ F.normalize(second, dim=-1).t() / temperature
    return (F.cross_entropy(logits, labels) + F.cross_entropy(logits.t(), labels)) / 2


def _augment(graph, edge_dropout: float, feature_dropout: float):
    view = graph.clone()
    for node_type in view.node_types:
        values = graph[node_type].x
        if values.numel() == 0:
            view[node_type].x = values.clone()
        else:
            mask = torch.rand_like(values) >= feature_dropout
            view[node_type].x = values * mask
    for edge_type in view.edge_types:
        edges = graph[edge_type].edge_index
        if edges.size(1) == 0:
            view[edge_type].edge_index = edges.clone()
            continue
        keep = torch.rand(edges.size(1), device=edges.device) >= edge_dropout
        view[edge_type].edge_index = edges[:, keep]
    return view


def train_encoder(graph, config: PretrainingConfig) -> HeteroGATEncoder:
    device = _device(config.device)
    graph = graph.to(device)
    encoder = HeteroGATEncoder.from_graph(
        graph,
        hidden_dim=config.hidden_dim,
        output_dim=config.output_dim,
        heads=config.heads,
        num_layers=config.num_layers,
        dropout=config.dropout,
    )
    model = PretrainingModel(encoder, config.interest_slots, config.interest_iterations).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
    best_loss = float("inf")
    best_encoder = None
    no_improvement = 0
    for _ in range(config.epochs):
        model.train()
        first = model(_augment(graph, config.edge_dropout, config.feature_dropout))
        second = model(_augment(graph, config.edge_dropout, config.feature_dropout))
        first_embeddings = first["embeddings"]["learner"]
        second_embeddings = second["embeddings"]["learner"]
        learner_loss = _contrastive(
            model.projector(first_embeddings), model.projector(second_embeddings), config.temperature
        )
        first_interests = first["interests"].reshape(-1, config.output_dim)
        second_interests = second["interests"].reshape(-1, config.output_dim)
        interest_loss = _contrastive(
            model.projector(first_interests), model.projector(second_interests), config.temperature
        )
        loss = learner_loss + interest_loss
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        current = float(loss.detach().cpu())
        if current < best_loss:
            best_loss = current
            best_encoder = copy.deepcopy(model.encoder.state_dict())
            no_improvement = 0
        else:
            no_improvement += 1
            if no_improvement >= config.patience:
                break
    if best_encoder is None:
        raise RuntimeError("graph encoder pretraining produced no checkpoint")
    encoder.load_state_dict(best_encoder)
    encoder.eval()
    return encoder
