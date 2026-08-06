"""A process-wide graph recommender retained for the FastAPI process lifetime."""

from __future__ import annotations

import asyncio
from pathlib import Path

from .data.types import GraphChange, GraphRows
from .data.repository import SqlAlchemyGraphRepository
from .features.embedding import EmbeddingProvider, SentenceTransformerEmbeddingProvider
from .runtime.recommender import GraphRecommender

_recommender: GraphRecommender | None = None
_load_lock = asyncio.Lock()
_BACKEND_DIR = Path(__file__).resolve().parents[2]


def resolve_checkpoint_dir(value: str | Path) -> Path:
    """Resolve a configured checkpoint directory relative to backend/ when needed."""
    directory = Path(value)
    return directory if directory.is_absolute() else _BACKEND_DIR / directory


async def load_graph_recommender() -> GraphRecommender:
    """Create and load the singleton once; intentionally do not clear it later."""
    global _recommender
    if _recommender is not None:
        return _recommender
    async with _load_lock:
        if _recommender is None:
            from app.config import settings

            config = settings.graph_recommender
            recommender = GraphRecommender(
                SqlAlchemyGraphRepository(),
                SentenceTransformerEmbeddingProvider(
                    config.embedding_model_id,
                ),
                resolve_checkpoint_dir(config.checkpoint_dir),
            )
            await recommender.start()
            _recommender = recommender
    return _recommender


def get_graph_recommender() -> GraphRecommender:
    """Return the already-loaded singleton for agent/tool code."""
    if _recommender is None:
        raise RuntimeError("graph recommender is not loaded; enable it in FastAPI startup first")
    return _recommender

__all__ = [
    "EmbeddingProvider",
    "GraphChange",
    "GraphRecommender",
    "GraphRows",
    "SentenceTransformerEmbeddingProvider",
    "get_graph_recommender",
    "load_graph_recommender",
    "resolve_checkpoint_dir",
]
