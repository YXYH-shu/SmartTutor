from __future__ import annotations

import pytest

from algorithm.graph_recommender.data.repository import InMemoryGraphRepository
from algorithm.graph_recommender.data.repository import SqlAlchemyGraphRepository
from algorithm.graph_recommender.data.types import CachedEmbedding, EmbeddingKey, ResourceRecord
from algorithm.graph_recommender.features.embedding import (
    EmbeddingResolver,
    HashEmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)
from algorithm.graph_recommender.features.text_templates import build_node_texts


class CountingHashEmbeddingProvider(HashEmbeddingProvider):
    def __init__(self, dimension: int = 8):
        super().__init__(dimension)
        self.calls = 0

    def encode(self, texts):
        self.calls += 1
        return super().encode(texts)


@pytest.mark.asyncio
async def test_embedding_cache_reuses_unchanged_text_and_invalidates_changed_node(graph_rows):
    repository = InMemoryGraphRepository(graph_rows)
    provider = HashEmbeddingProvider(dimension=6)
    resolver = EmbeddingResolver(repository, provider)

    first = await resolver.resolve(graph_rows)
    assert len(first) == 8
    assert len(repository.upserted) == 8

    second = await resolver.resolve(graph_rows)
    assert second == first
    assert len(repository.upserted) == 8

    graph_rows.resources[0] = ResourceRecord("r1", "updated resource")
    third = await resolver.resolve(graph_rows)
    assert third != first
    assert len(repository.upserted) == 9

    await EmbeddingResolver(repository, HashEmbeddingProvider(dimension=7, model_id="test/new-model")).resolve(
        graph_rows
    )
    assert len(repository.upserted) == 17


@pytest.mark.asyncio
async def test_incremental_cache_skips_encoding_for_unchanged_nodes(graph_rows):
    repository = InMemoryGraphRepository(graph_rows)
    provider = CountingHashEmbeddingProvider(dimension=6)
    resolver = EmbeddingResolver(repository, provider)

    await resolver.resolve(graph_rows, embedding_dimension=6, verify_cache=False)
    assert provider.calls == 1

    await resolver.resolve(graph_rows, embedding_dimension=6, verify_cache=False)
    assert provider.calls == 1

    graph_rows.resources[0] = ResourceRecord("r1", "updated resource")
    await resolver.resolve(
        graph_rows,
        embedding_dimension=6,
        verify_cache=False,
        force_keys=[EmbeddingKey("resource", "r1")],
    )
    assert provider.calls == 2


def test_learner_template_excludes_identity_fields(graph_rows):
    graph_rows.learners[0] = graph_rows.learners[0].__class__(
        "u1",
        {
            "learning_style": "visual",
            "username": "private-name",
            "email": "private@example.com",
            "hashed_password": "do-not-leak",
        },
    )
    learner_text = build_node_texts(graph_rows)["learner"]["u1"]
    assert "private-name" not in learner_text
    assert "private@example.com" not in learner_text
    assert "do-not-leak" not in learner_text


def test_configured_embedding_dimension_does_not_load_encoder_for_cache_validation():
    provider = SentenceTransformerEmbeddingProvider("BAAI/bge-small-zh-v1.5", dimension=512)

    assert provider.dimension == 512
    assert provider._model is None


@pytest.mark.asyncio
async def test_sqlalchemy_embedding_cache_round_trip():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.database import Base
    from app.models.graph_node_embedding import GraphNodeEmbedding

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    repository = SqlAlchemyGraphRepository(factory)
    key = EmbeddingKey("resource", "r1")
    await repository.upsert_embeddings(
        [CachedEmbedding(key, "model", "v1", "hash", 2, [0.1, 0.2])]
    )
    loaded = await repository.load_embeddings([key], "model", "v1")
    assert loaded[key].vector == [0.1, 0.2]
    await repository.upsert_embeddings(
        [CachedEmbedding(key, "model", "v1", "new-hash", 2, [0.3, 0.4])]
    )
    loaded = await repository.load_embeddings([key], "model", "v1")
    assert loaded[key].text_hash == "new-hash"
    assert loaded[key].vector == [0.3, 0.4]
    await engine.dispose()
