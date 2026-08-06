from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
import torch

from algorithm.graph_recommender.data.graph_builder import GraphBuilder, GraphData
from algorithm.graph_recommender.data.repository import InMemoryGraphRepository
from algorithm.graph_recommender.data.types import CachedEmbedding, EmbeddingKey, GraphChange, GraphRows
from algorithm.graph_recommender.features.embedding import HashEmbeddingProvider
from algorithm.graph_recommender.models.checkpoints import (
    GraphModelConfig,
    load_checkpoints,
    require_checkpoint_files,
    save_checkpoints,
)
from algorithm.graph_recommender.models.hetero_gat import HeteroGATEncoder, MLPScorer
from algorithm.graph_recommender.runtime.recommender import GraphRecommender, GraphSnapshot, GraphSyncManager


def _model_config(embedding_dim: int, hidden_dim: int = 64) -> GraphModelConfig:
    return GraphModelConfig(
        embedding_dim=embedding_dim,
        embedding_batch_size=32,
        hidden_dim=hidden_dim,
        output_dim=hidden_dim,
        heads=2,
        num_layers=2,
        dropout=0.2,
        pretraining_epochs=100,
        pretraining_learning_rate=1e-3,
        pretraining_weight_decay=1e-4,
        edge_dropout=0.1,
        feature_dropout=0.1,
        temperature=0.2,
        pretraining_patience=20,
        interest_slots=4,
        interest_iterations=3,
        task_epochs=100,
        task_learning_rate=1e-3,
        task_weight_decay=0.0,
        negatives_per_positive=5,
        task_seed=42,
    )


def test_checkpoint_files_are_required(tmp_path):
    with pytest.raises(FileNotFoundError, match="encoder.pt"):
        require_checkpoint_files(tmp_path)


def test_checkpoints_save_only_model_weights_not_node_embeddings(tmp_path):
    encoder = torch.nn.Linear(4, 4)
    resource = MLPScorer(4)
    peer = MLPScorer(4)
    save_checkpoints(
        tmp_path,
        encoder=encoder,
        resource_scorer=resource,
        peer_scorer=peer,
        model_config=_model_config(4, 4),
    )
    assert {path.name for path in tmp_path.iterdir()} == {
        "encoder.pt",
        "resource_scorer.pt",
        "peer_scorer.pt",
        "model_config.json",
    }
    state = torch.load(tmp_path / "encoder.pt", weights_only=True)
    assert all("embedding" not in key for key in state)
    saved_config = GraphModelConfig.load(tmp_path)
    assert saved_config.embedding_dim == 4
    assert saved_config.embedding_batch_size == 32


def _snapshot() -> GraphSnapshot:
    node_ids = {
        "learner": ["u1", "u2", "u3"],
        "resource": ["r1", "r2", "r3"],
        "knowledge_point": [],
    }
    id_to_index = {kind: {value: index for index, value in enumerate(values)} for kind, values in node_ids.items()}
    graph_data = GraphData(
        node_features={
            "learner": torch.zeros((3, 4)),
            "resource": torch.tensor(
                [
                    [1.0, 0.0, 0.0, 0.0],
                    [0.8, 0.6, 0.0, 0.0],
                    [0.0, 1.0, 0.0, 0.0],
                ]
            ),
            "knowledge_point": torch.empty((0, 4)),
        },
        edge_index={},
        node_ids=node_ids,
        id_to_index=id_to_index,
        seen_resources={"u1": {"r1"}},
        partners={"u1": {"u2"}},
    )
    return GraphSnapshot.create(
        1,
        graph_data,
        graph=None,
    )


def test_ranking_keeps_seen_resources_and_filters_existing_peers(tmp_path):
    recommender = GraphRecommender(
        InMemoryGraphRepository(GraphRows()), HashEmbeddingProvider(4), tmp_path
    )
    scorer = MLPScorer(4)
    for parameter in scorer.parameters():
        parameter.data.zero_()
    recommender._snapshot = _snapshot()
    recommender._resource_scorer = scorer
    recommender._peer_scorer = scorer
    recommender._forward_graph = MagicMock(
        return_value={
            "learner": torch.ones((3, 4)),
            "resource": torch.ones((3, 4)),
            "knowledge_point": torch.empty((0, 4)),
        }
    )

    resources = recommender.rank_resources("u1", ["r1", "r2", "unknown"], 5)
    peers = recommender.rank_peers("u1", ["u1", "u2", "u3"], 5)
    assert {item.id for item in resources} == {"r1", "r2"}
    assert [item.id for item in peers] == ["u3"]
    assert recommender._forward_graph.call_count == 2


def test_peer_similarity_uses_gat_and_resource_similarity_returns_text_embedding_pairs(tmp_path):
    recommender = GraphRecommender(
        InMemoryGraphRepository(GraphRows()), HashEmbeddingProvider(4), tmp_path
    )
    snapshot = _snapshot()
    encoded_nodes = {
        "learner": torch.tensor(
            [
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [0.6, 0.8, 0.0, 0.0],
            ]
        ),
        "resource": torch.tensor(
            [
                [1.0, 0.0, 0.0, 0.0],
                [0.8, 0.6, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
            ]
        ),
        "knowledge_point": torch.empty((0, 4)),
    }
    scorer = MLPScorer(4)
    recommender._snapshot = snapshot
    recommender._resource_scorer = scorer
    recommender._peer_scorer = scorer
    recommender._forward_graph = MagicMock(return_value=encoded_nodes)

    peers = recommender.similar_peers(
        "u1",
        ["u1", "u2", "u3", "unknown"],
        5,
        include_existing_partners=True,
    )
    filtered_peers = recommender.similar_peers("u1", ["u1", "u2", "u3"], 5)
    related_resources = recommender.rank_resource_similarity_pairs(["r1"], 5)
    multi_anchor_pairs = recommender.rank_resource_similarity_pairs(["r1", "r3"], 5)

    assert [item.id for item in peers] == ["u3", "u2"]
    assert peers[0].score == pytest.approx(0.6)
    assert [item.id for item in filtered_peers] == ["u3"]
    assert [item.id for item in related_resources] == ["r2", "r3"]
    assert [item.reference_id for item in related_resources] == ["r1", "r1"]
    assert related_resources[0].score == pytest.approx(0.8)
    assert [item.id for item in multi_anchor_pairs] == ["r2", "r2"]
    assert [item.reference_id for item in multi_anchor_pairs] == ["r1", "r3"]
    assert recommender._forward_graph.call_count == 2


class _Refreshable:
    def __init__(self):
        self.calls = 0
        self.changes = None

    async def refresh_full(self, *, changes=None):
        self.calls += 1
        self.changes = list(changes or ())
        return self.calls


@pytest.mark.asyncio
async def test_sync_deletes_embedding_after_commit_then_refreshes():
    key = EmbeddingKey("resource", "r1")
    record = CachedEmbedding(key, "test", "v1", "hash", 2, [0.1, 0.2])
    repository = InMemoryGraphRepository(GraphRows(), [record])
    refreshable = _Refreshable()
    manager = GraphSyncManager(repository, refreshable)
    result = await manager.sync_after_commit([GraphChange("delete", "resource", entity_id="r1")])
    assert result == 1
    assert key not in repository.embeddings


def test_interaction_sync_does_not_refresh_node_embeddings():
    force_keys, verify_cache = GraphRecommender._embedding_refresh_plan(
        [
            GraphChange(
                "upsert",
                "edge",
                relation_type="interacted_with",
                source_id="u1",
                target_id="r1",
            )
        ]
    )

    assert force_keys == set()
    assert verify_cache is False


def test_relation_deletion_refreshes_affected_node_embedding():
    force_keys, verify_cache = GraphRecommender._embedding_refresh_plan(
        [
            GraphChange(
                "delete",
                "edge",
                relation_type="covers",
                source_id="r1",
                target_id="k1",
            )
        ]
    )

    assert force_keys == {EmbeddingKey("resource", "r1")}
    assert verify_cache is False


@pytest.mark.asyncio
async def test_checkpoint_loads_without_task_edges(tmp_path, graph_rows):
    pytest.importorskip("torch_geometric")
    graph_rows.resource_interactions = []
    graph_rows.partner_relations = []
    repository = InMemoryGraphRepository(graph_rows)
    provider = HashEmbeddingProvider(dimension=8)
    rows = await repository.load_rows()
    embeddings = await GraphRecommender(repository, provider, tmp_path, device="cpu")._resolver.resolve(rows)
    graph = GraphBuilder().build(
        rows,
        embeddings,
        embedding_dimension=provider.dimension,
    ).to_heterodata()
    encoder = HeteroGATEncoder.from_graph(graph, hidden_dim=64, output_dim=64, heads=2, num_layers=2, dropout=0.2)
    save_checkpoints(
        tmp_path,
        encoder=encoder,
        resource_scorer=MLPScorer(64),
        peer_scorer=MLPScorer(64),
        model_config=_model_config(8),
    )
    loaded_encoder, _, _ = load_checkpoints(tmp_path, graph=graph, device=torch.device("cpu"))
    assert loaded_encoder.output_dim == 64

    recommender = GraphRecommender(repository, provider, tmp_path, device="cpu")
    await recommender.start()
    status = recommender.get_status()
    assert status["ready"] is True
    ranked = recommender.rank_resources("u1", ["r2", "r3", "unknown"], 2)
    assert {item.id for item in ranked} <= {"r2", "r3"}
