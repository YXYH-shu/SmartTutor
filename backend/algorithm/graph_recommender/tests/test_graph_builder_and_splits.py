from __future__ import annotations

from datetime import datetime, timedelta, timezone

from algorithm.graph_recommender.data.audit import audit_rows
from algorithm.graph_recommender.data.graph_builder import GraphBuilder
from algorithm.graph_recommender.data.splits import split_peer_relations, split_resource_interactions
from algorithm.graph_recommender.data.types import EmbeddingKey, GraphRows, PartnerRelation
from algorithm.graph_recommender.features.embedding import HashEmbeddingProvider
from algorithm.graph_recommender.features.text_templates import build_node_texts


def _vectors(rows):
    provider = HashEmbeddingProvider(4)
    return {
        EmbeddingKey(node_type, node_id): vector
        for node_type, per_type in build_node_texts(rows).items()
        for node_id, vector in zip(per_type, provider.encode(list(per_type.values())), strict=True)
    }


def test_graph_builder_adds_reverse_edges_and_valid_fallbacks(graph_rows):
    graph = GraphBuilder().build(graph_rows, _vectors(graph_rows))
    learner_edges = graph.edge_index[("learner", "interacted_with", "resource")]
    reverse_edges = graph.edge_index[("resource", "rev_interacted_with", "learner")]
    covers = graph.edge_index[("resource", "covers", "knowledge_point")]
    states = graph.edge_index[("learner", "has_knowledge_state", "knowledge_point")]
    precedes = graph.edge_index[("knowledge_point", "precedes", "knowledge_point")]
    partners = graph.edge_index[("learner", "partnered_with", "learner")]

    assert learner_edges.size(1) == reverse_edges.size(1) == 3
    assert covers.size(1) == 2  # r2 uses knowledge_coverage only because it has no table relation.
    assert states.size(1) == 2  # profile k1 and learner_knowledge_interactions k2.
    assert precedes.size(1) == 1  # k2.pre_knowledge fallback creates k1 -> k2.
    assert partners.size(1) == 6  # three canonical pairs, stored both directions.


def test_empty_graph_keeps_configured_embedding_dimension():
    graph = GraphBuilder().build(GraphRows(), {}, embedding_dimension=512)

    assert {features.shape for features in graph.node_features.values()} == {(0, 512)}


def test_temporal_splits_keep_holdouts_out_of_training_graph(graph_rows):
    resource_splits = split_resource_interactions(graph_rows.resource_interactions)
    assert resource_splits.train == {("u1", "r1")}
    assert resource_splits.validation == {("u1", "r2")}
    assert resource_splits.test == {("u1", "r3")}
    assert not (resource_splits.train & resource_splits.validation)
    assert not (resource_splits.train & resource_splits.test)

    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    relations = [
        PartnerRelation(f"u{index}", f"u{index + 1}", origin + timedelta(days=index))
        for index in range(20)
    ]
    peer_splits = split_peer_relations(relations)
    assert len(peer_splits.train) == 16
    assert len(peer_splits.validation) == 2
    assert len(peer_splits.test) == 2
    assert not (peer_splits.train & peer_splits.validation)
    assert not (peer_splits.train & peer_splits.test)


def test_audit_reports_duplicate_interactions(graph_rows):
    report = audit_rows(graph_rows)
    assert report["duplicates"]["learner_resource"] == 1
    assert report["orphans"]["learner_resource"] == 0
