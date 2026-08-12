"""Persistence for the graph encoder and its two task heads."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import torch

WEIGHT_FILES = ("encoder.pt", "resource_scorer.pt", "peer_scorer.pt")
MODEL_CONFIG_FILE = "model_config.json"
CHECKPOINT_FILES = WEIGHT_FILES + (MODEL_CONFIG_FILE,)


@dataclass(frozen=True)
class GraphModelConfig:
    embedding_dim: int
    embedding_batch_size: int
    hidden_dim: int
    output_dim: int
    heads: int
    num_layers: int
    dropout: float
    pretraining_epochs: int
    pretraining_learning_rate: float
    pretraining_weight_decay: float
    edge_dropout: float
    feature_dropout: float
    temperature: float
    pretraining_patience: int
    interest_slots: int
    interest_iterations: int
    task_epochs: int
    task_learning_rate: float
    task_weight_decay: float
    negatives_per_positive: int
    task_seed: int

    @classmethod
    def load(cls, checkpoint_dir: str | Path) -> "GraphModelConfig":
        directory = require_checkpoint_files(checkpoint_dir)
        try:
            with (directory / MODEL_CONFIG_FILE).open("r", encoding="utf-8") as handle:
                values = json.load(handle)
            config = cls(**values)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid graph recommender model config in {directory}") from exc
        if (
            config.embedding_dim <= 0
            or config.embedding_batch_size <= 0
            or config.hidden_dim <= 0
            or config.output_dim <= 0
            or config.heads <= 0
            or config.num_layers <= 0
            or config.pretraining_epochs <= 0
            or config.pretraining_learning_rate <= 0
            or config.pretraining_weight_decay < 0
            or config.pretraining_patience <= 0
            or config.interest_slots <= 0
            or config.interest_iterations <= 0
            or config.task_epochs <= 0
            or config.task_learning_rate <= 0
            or config.task_weight_decay < 0
            or config.negatives_per_positive <= 0
            or not 0 <= config.edge_dropout < 1
            or not 0 <= config.feature_dropout < 1
            or not 0 <= config.dropout < 1
            or config.temperature <= 0
        ):
            raise ValueError(f"invalid graph recommender model config in {directory}")
        return config

    def save(self, checkpoint_dir: str | Path) -> None:
        directory = Path(checkpoint_dir)
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / MODEL_CONFIG_FILE).open("w", encoding="utf-8") as handle:
            json.dump(asdict(self), handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")


def require_checkpoint_files(checkpoint_dir: str | Path) -> Path:
    directory = Path(checkpoint_dir)
    missing = [name for name in CHECKPOINT_FILES if not (directory / name).is_file()]
    if missing:
        raise FileNotFoundError(
            f"missing graph recommender checkpoint files in {directory}: {', '.join(missing)}"
        )
    return directory


def save_checkpoints(
    checkpoint_dir: str | Path,
    *,
    encoder,
    resource_scorer,
    peer_scorer,
    model_config: GraphModelConfig,
) -> None:
    directory = Path(checkpoint_dir)
    directory.mkdir(parents=True, exist_ok=True)
    torch.save(encoder.state_dict(), directory / "encoder.pt")
    torch.save(resource_scorer.state_dict(), directory / "resource_scorer.pt")
    torch.save(peer_scorer.state_dict(), directory / "peer_scorer.pt")
    model_config.save(directory)


def load_checkpoints(
    checkpoint_dir: str | Path,
    *,
    graph,
    device: torch.device,
    model_config: GraphModelConfig | None = None,
):
    from .hetero_gat import HeteroGATEncoder, MLPScorer

    directory = require_checkpoint_files(checkpoint_dir)
    config = model_config or GraphModelConfig.load(directory)
    graph_dimensions = {graph[node_type].x.size(-1) for node_type in graph.node_types}
    if graph_dimensions != {config.embedding_dim}:
        raise ValueError(
            "graph embedding dimension does not match model_config.json: "
            f"expected {config.embedding_dim}, got {sorted(graph_dimensions)}"
        )
    encoder = HeteroGATEncoder.from_graph(
        graph,
        hidden_dim=config.hidden_dim,
        output_dim=config.output_dim,
        heads=config.heads,
        num_layers=config.num_layers,
        dropout=config.dropout,
    ).to(device)
    resource_scorer = MLPScorer(config.output_dim).to(device)
    peer_scorer = MLPScorer(config.output_dim).to(device)
    try:
        encoder.load_state_dict(torch.load(directory / "encoder.pt", map_location=device, weights_only=True))
        resource_scorer.load_state_dict(
            torch.load(directory / "resource_scorer.pt", map_location=device, weights_only=True)
        )
        peer_scorer.load_state_dict(
            torch.load(directory / "peer_scorer.pt", map_location=device, weights_only=True)
        )
    except RuntimeError as exc:
        raise ValueError(f"incompatible graph recommender checkpoint: {exc}") from exc
    encoder.eval()
    resource_scorer.eval()
    peer_scorer.eval()
    return encoder, resource_scorer, peer_scorer
