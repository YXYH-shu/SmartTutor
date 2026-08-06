"""Build the fixed heterogeneous education graph from current business records."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

import torch

from .types import EmbeddingKey, GraphRows

NODE_TYPES = ("learner", "resource", "knowledge_point")
FORWARD_RELATIONS = (
    ("learner", "interacted_with", "resource"),
    ("resource", "covers", "knowledge_point"),
    ("learner", "has_knowledge_state", "knowledge_point"),
    ("knowledge_point", "precedes", "knowledge_point"),
    ("learner", "partnered_with", "learner"),
)
REVERSE_RELATIONS = (
    ("resource", "rev_interacted_with", "learner"),
    ("knowledge_point", "rev_covers", "resource"),
    ("knowledge_point", "rev_has_knowledge_state", "learner"),
)
RELATION_TYPES = FORWARD_RELATIONS + REVERSE_RELATIONS


def _ids_from_json(raw: Any) -> set[str]:
    if isinstance(raw, dict):
        return {str(key) for key in raw}
    if isinstance(raw, (list, tuple, set)):
        values = set()
        for item in raw:
            if isinstance(item, dict):
                for key in ("id", "kp_id", "knowledge_id"):
                    if item.get(key) is not None:
                        values.add(str(item[key]))
                        break
            elif item is not None:
                values.add(str(item))
        return values
    return set()


@dataclass
class GraphData:
    node_features: dict[str, torch.Tensor]
    edge_index: dict[tuple[str, str, str], torch.Tensor]
    node_ids: dict[str, list[str]]
    id_to_index: dict[str, dict[str, int]]
    seen_resources: dict[str, set[str]]
    partners: dict[str, set[str]]

    @property
    def metadata(self) -> tuple[list[str], list[tuple[str, str, str]]]:
        return list(NODE_TYPES), list(RELATION_TYPES)

    def to_heterodata(self):
        """Convert to PyG only when graph model code is actually invoked."""
        try:
            from torch_geometric.data import HeteroData
        except ImportError as exc:
            raise RuntimeError(
                "torch-geometric is required to create the graph recommendation model."
            ) from exc
        data = HeteroData()
        for node_type in NODE_TYPES:
            data[node_type].x = self.node_features[node_type]
            data[node_type].num_nodes = len(self.node_ids[node_type])
        for relation in RELATION_TYPES:
            data[relation].edge_index = self.edge_index[relation]
        return data


class GraphBuilder:
    """Constructs a stable schema even when one or more relations are empty."""

    def build(
        self,
        rows: GraphRows,
        embeddings: dict[EmbeddingKey, list[float]],
        *,
        excluded_resource_edges: Iterable[tuple[str, str]] = (),
        excluded_partner_edges: Iterable[tuple[str, str]] = (),
        embedding_dimension: int | None = None,
    ) -> GraphData:
        node_ids = {
            "learner": sorted({row.id for row in rows.learners}),
            "resource": sorted({row.id for row in rows.resources}),
            "knowledge_point": sorted({row.id for row in rows.knowledge_points}),
        }
        id_to_index = {
            node_type: {node_id: index for index, node_id in enumerate(ids)}
            for node_type, ids in node_ids.items()
        }
        resolved_dimension = (
            len(next(iter(embeddings.values())))
            if embeddings
            else (embedding_dimension or 0)
        )
        node_features = {
            node_type: self._features(node_type, ids, embeddings, resolved_dimension)
            for node_type, ids in node_ids.items()
        }
        edge_sets: dict[tuple[str, str, str], set[tuple[int, int]]] = {
            relation: set() for relation in RELATION_TYPES
        }
        seen_resources: dict[str, set[str]] = defaultdict(set)
        partners: dict[str, set[str]] = defaultdict(set)
        excluded_resource_edges = set(excluded_resource_edges)
        excluded_partner_edges = {tuple(sorted(pair)) for pair in excluded_partner_edges}

        learners, resources, points = (
            id_to_index["learner"],
            id_to_index["resource"],
            id_to_index["knowledge_point"],
        )

        for row in rows.resource_interactions:
            if row.learner_id not in learners or row.resource_id not in resources:
                continue
            seen_resources[row.learner_id].add(row.resource_id)
            if (row.learner_id, row.resource_id) in excluded_resource_edges:
                continue
            self._add_bidirectional(
                edge_sets,
                ("learner", "interacted_with", "resource"),
                ("resource", "rev_interacted_with", "learner"),
                learners[row.learner_id],
                resources[row.resource_id],
            )

        direct_resource_knowledge: dict[str, set[str]] = defaultdict(set)
        for row in rows.resource_knowledge:
            if row.resource_id in resources and row.knowledge_id in points:
                direct_resource_knowledge[row.resource_id].add(row.knowledge_id)
        resource_records = {row.id: row for row in rows.resources}
        for resource_id in resources:
            knowledge_ids = direct_resource_knowledge.get(resource_id)
            if not knowledge_ids:
                knowledge_ids = {
                    knowledge_id
                    for knowledge_id in _ids_from_json(resource_records[resource_id].knowledge_coverage)
                    if knowledge_id in points
                }
            for knowledge_id in knowledge_ids:
                self._add_bidirectional(
                    edge_sets,
                    ("resource", "covers", "knowledge_point"),
                    ("knowledge_point", "rev_covers", "resource"),
                    resources[resource_id],
                    points[knowledge_id],
                )

        state_pairs: set[tuple[str, str]] = set()
        for row in rows.knowledge_states:
            if row.learner_id in learners and row.knowledge_id in points:
                state_pairs.add((row.learner_id, row.knowledge_id))
        for learner in rows.learners:
            for knowledge_id in _ids_from_json(learner.knowledge_graph):
                if learner.id in learners and knowledge_id in points:
                    state_pairs.add((learner.id, knowledge_id))
        for learner_id, knowledge_id in state_pairs:
            self._add_bidirectional(
                edge_sets,
                ("learner", "has_knowledge_state", "knowledge_point"),
                ("knowledge_point", "rev_has_knowledge_state", "learner"),
                learners[learner_id],
                points[knowledge_id],
            )

        direct_prerequisites: dict[str, set[str]] = defaultdict(set)
        for row in rows.knowledge_prerequisites:
            if row.source_id in points and row.target_id in points and row.source_id != row.target_id:
                direct_prerequisites[row.target_id].add(row.source_id)
        point_records = {row.id: row for row in rows.knowledge_points}
        for target_id in points:
            source_ids = direct_prerequisites.get(target_id)
            if not source_ids:
                source_ids = {
                    source_id
                    for source_id in _ids_from_json(point_records[target_id].pre_knowledge)
                    if source_id in points and source_id != target_id
                }
            for source_id in source_ids:
                edge_sets[("knowledge_point", "precedes", "knowledge_point")].add(
                    (points[source_id], points[target_id])
                )

        for row in rows.partner_relations:
            pair = tuple(sorted((row.learner_a_id, row.learner_b_id)))
            if (
                row.learner_a_id not in learners
                or row.learner_b_id not in learners
                or row.learner_a_id == row.learner_b_id
            ):
                continue
            partners[row.learner_a_id].add(row.learner_b_id)
            partners[row.learner_b_id].add(row.learner_a_id)
            if pair in excluded_partner_edges:
                continue
            edge_sets[("learner", "partnered_with", "learner")].update(
                {
                    (learners[row.learner_a_id], learners[row.learner_b_id]),
                    (learners[row.learner_b_id], learners[row.learner_a_id]),
                }
            )

        edge_index = {
            relation: self._edge_tensor(pairs)
            for relation, pairs in edge_sets.items()
        }
        return GraphData(
            node_features=node_features,
            edge_index=edge_index,
            node_ids=node_ids,
            id_to_index=id_to_index,
            seen_resources={key: set(value) for key, value in seen_resources.items()},
            partners={key: set(value) for key, value in partners.items()},
        )

    @staticmethod
    def _features(
        node_type: str,
        ids: list[str],
        embeddings: dict[EmbeddingKey, list[float]],
        embedding_dimension: int,
    ) -> torch.Tensor:
        vectors = []
        dimension: int | None = None
        for node_id in ids:
            vector = embeddings.get(EmbeddingKey(node_type, node_id))
            if vector is None:
                raise ValueError(f"missing embedding for {node_type}:{node_id}")
            if dimension is None:
                dimension = len(vector)
            elif len(vector) != dimension:
                raise ValueError(f"inconsistent embedding dimension for {node_type}")
            vectors.append(vector)
        if not vectors:
            # BGE dimensions are known before graph construction; use a safe empty tensor here.
            return torch.empty((0, embedding_dimension), dtype=torch.float32)
        return torch.tensor(vectors, dtype=torch.float32)

    @staticmethod
    def _edge_tensor(pairs: set[tuple[int, int]]) -> torch.Tensor:
        if not pairs:
            return torch.empty((2, 0), dtype=torch.long)
        ordered = sorted(pairs)
        return torch.tensor(ordered, dtype=torch.long).t().contiguous()

    @staticmethod
    def _add_bidirectional(
        edge_sets: dict[tuple[str, str, str], set[tuple[int, int]]],
        forward: tuple[str, str, str],
        reverse: tuple[str, str, str],
        source: int,
        target: int,
    ) -> None:
        edge_sets[forward].add((source, target))
        edge_sets[reverse].add((target, source))
