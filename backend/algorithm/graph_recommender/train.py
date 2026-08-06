"""Single training entry point for the graph recommender.

Run from the backend directory with:
    python algorithm/graph_recommender/train.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Direct ``python .../train.py`` execution needs backend on sys.path.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.config import settings
from algorithm.graph_recommender import resolve_checkpoint_dir
from algorithm.graph_recommender.data.audit import audit_rows
from algorithm.graph_recommender.data.repository import SqlAlchemyGraphRepository
from algorithm.graph_recommender.features.embedding import SentenceTransformerEmbeddingProvider
from algorithm.graph_recommender.models.checkpoints import GraphModelConfig
from algorithm.graph_recommender.training.pipeline import (
    TrainingConfig,
    train_from_repository,
)
from algorithm.graph_recommender.training.pretrain import PretrainingConfig
from algorithm.graph_recommender.training.tasks import TaskTrainingConfig


async def _require_embedding_cache_table() -> None:
    from sqlalchemy import inspect

    from app.database import engine

    async with engine.connect() as connection:
        exists = await connection.run_sync(
            lambda sync_connection: inspect(sync_connection).has_table("graph_node_embeddings")
        )
    if not exists:
        raise RuntimeError(
            "missing graph_node_embeddings table; run `alembic upgrade head` before graph training"
        )


async def train(
) -> dict[str, object]:
    graph_settings = settings.graph_recommender
    checkpoint_dir = resolve_checkpoint_dir(graph_settings.checkpoint_dir)
    model_config = GraphModelConfig.load(checkpoint_dir)
    provider = SentenceTransformerEmbeddingProvider(
        graph_settings.embedding_model_id,
        batch_size=model_config.embedding_batch_size,
        dimension=model_config.embedding_dim,
    )
    repository = SqlAlchemyGraphRepository()
    await _require_embedding_cache_table()
    rows = await repository.load_rows()
    audit = audit_rows(rows)
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    pretraining = PretrainingConfig(
        epochs=model_config.pretraining_epochs,
        learning_rate=model_config.pretraining_learning_rate,
        weight_decay=model_config.pretraining_weight_decay,
        hidden_dim=model_config.hidden_dim,
        output_dim=model_config.output_dim,
        heads=model_config.heads,
        num_layers=model_config.num_layers,
        dropout=model_config.dropout,
        edge_dropout=model_config.edge_dropout,
        feature_dropout=model_config.feature_dropout,
        temperature=model_config.temperature,
        patience=model_config.pretraining_patience,
        interest_slots=model_config.interest_slots,
        interest_iterations=model_config.interest_iterations,
    )
    tasks = TaskTrainingConfig(
        epochs=model_config.task_epochs,
        learning_rate=model_config.task_learning_rate,
        weight_decay=model_config.task_weight_decay,
        negatives_per_positive=model_config.negatives_per_positive,
        seed=model_config.task_seed,
    )
    training_config = TrainingConfig(
        checkpoint_dir=checkpoint_dir,
        model_config=model_config,
        pretraining=pretraining,
        tasks=tasks,
    )
    metrics = await train_from_repository(repository, provider, training_config)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="Train the Smart Tutor graph recommender")
    parser.parse_args()
    asyncio.run(train())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
