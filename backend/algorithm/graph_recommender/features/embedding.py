"""Frozen text-embedding providers used only to create node features."""

from __future__ import annotations

import asyncio
import hashlib
from typing import Iterable, Protocol, Sequence

from algorithm.graph_recommender.data.repository import GraphRepository
from algorithm.graph_recommender.data.types import CachedEmbedding, EmbeddingKey, GraphRows

from .text_templates import TEXT_TEMPLATE_VERSION, build_node_texts, text_hash


class EmbeddingProvider(Protocol):
    model_id: str

    @property
    def dimension(self) -> int: ...

    def encode(self, texts: Sequence[str]) -> list[list[float]]: ...


class SentenceTransformerEmbeddingProvider:
    """Lazy SentenceTransformer wrapper so importing the package stays light."""

    def __init__(
        self,
        model_id: str = "BAAI/bge-small-zh-v1.5",
        *,
        device: str | None = None,
        batch_size: int = 32,
        dimension: int | None = None,
    ):
        self.model_id = model_id
        self.device = device
        self.batch_size = batch_size
        self._model = None
        self._dimension = dimension

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "sentence-transformers is required for graph node embeddings. "
                    "Install backend requirements before creating the graph."
                ) from exc
            self._model = SentenceTransformer(self.model_id, device=self.device)
            model_dimension = int(self._model.get_sentence_embedding_dimension())
            if self._dimension is not None and self._dimension != model_dimension:
                raise RuntimeError(
                    f"configured embedding dimension {self._dimension} does not match "
                    f"{self.model_id} dimension {model_dimension}"
                )
            self._dimension = model_dimension
        return self._model

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self._get_model()
        assert self._dimension is not None
        return self._dimension

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._get_model()
        matrix = model.encode(
            list(texts),
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [[float(value) for value in row] for row in matrix]


class HashEmbeddingProvider:
    """Deterministic test provider. It is intentionally unsuitable for production."""

    def __init__(self, dimension: int = 8, model_id: str = "test/hash-embedding"):
        self.model_id = model_id
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            values = [digest[index % len(digest)] / 127.5 - 1.0 for index in range(self.dimension)]
            vectors.append(values)
        return vectors


class EmbeddingResolver:
    """Resolve durable vectors first and only encode missing or stale node text."""

    def __init__(
        self,
        repository: GraphRepository,
        provider: EmbeddingProvider,
        *,
        template_version: str = TEXT_TEMPLATE_VERSION,
    ):
        self.repository = repository
        self.provider = provider
        self.template_version = template_version

    async def resolve(
        self,
        rows: GraphRows,
        *,
        embedding_dimension: int | None = None,
        verify_cache: bool = True,
        force_keys: Iterable[EmbeddingKey] = (),
    ) -> dict[EmbeddingKey, list[float]]:
        keys = [
            *(EmbeddingKey("learner", row.id) for row in rows.learners),
            *(EmbeddingKey("resource", row.id) for row in rows.resources),
            *(EmbeddingKey("knowledge_point", row.id) for row in rows.knowledge_points),
        ]
        cached = await self.repository.load_embeddings(
            keys, self.provider.model_id, self.template_version
        )
        expected_dimension = embedding_dimension or self.provider.dimension
        force = set(force_keys) & set(keys)
        invalid = {
            key
            for key in keys
            if (record := cached.get(key)) is None
            or record.dimension != expected_dimension
            or len(record.vector) != expected_dimension
        }
        text_keys = set(keys) if verify_cache else force | invalid
        texts = build_node_texts(rows, text_keys)
        resolved: dict[EmbeddingKey, list[float]] = {}
        missing: list[tuple[EmbeddingKey, str]] = []
        for key in keys:
            record = cached.get(key)
            text = texts.get(key.entity_type, {}).get(key.entity_id)
            if (
                record is not None
                and record.dimension == expected_dimension
                and len(record.vector) == expected_dimension
                and key not in force
                and (not verify_cache or record.text_hash == text_hash(text))
            ):
                resolved[key] = record.vector
            else:
                if text is None:
                    raise RuntimeError(f"missing node text for {key.entity_type}:{key.entity_id}")
                missing.append((key, text))
        if missing:
            vectors = await asyncio.to_thread(self.provider.encode, [text for _, text in missing])
            if len(vectors) != len(missing):
                raise RuntimeError("embedding provider returned an unexpected number of vectors")
            fresh = []
            for (key, text), vector in zip(missing, vectors, strict=True):
                if len(vector) != expected_dimension:
                    raise RuntimeError(f"embedding dimension mismatch for {key.entity_type}:{key.entity_id}")
                fresh.append(
                    CachedEmbedding(
                        key=key,
                        model_id=self.provider.model_id,
                        template_version=self.template_version,
                        text_hash=text_hash(text),
                        dimension=expected_dimension,
                        vector=vector,
                    )
                )
                resolved[key] = vector
            await self.repository.upsert_embeddings(fresh)
        return resolved
