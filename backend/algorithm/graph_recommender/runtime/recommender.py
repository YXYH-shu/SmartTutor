"""Long-lived graph structure with request-time GAT inference."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import torch
import torch.nn.functional as F

from algorithm.graph_recommender.data.graph_builder import GraphBuilder
from algorithm.graph_recommender.data.repository import GraphRepository
from algorithm.graph_recommender.data.types import EmbeddingKey, GraphChange
from algorithm.graph_recommender.features.embedding import EmbeddingProvider, EmbeddingResolver
from algorithm.graph_recommender.features.text_templates import TEXT_TEMPLATE_VERSION
from algorithm.graph_recommender.models.checkpoints import (
    GraphModelConfig,
    load_checkpoints,
)
from algorithm.graph_recommender.models.hetero_gat import symmetric_logits

@dataclass(frozen=True)
class RankedItem:
    id: str
    score: float


@dataclass(frozen=True)
class ResourceSimilarityPair:
    id: str
    reference_id: str
    score: float


@dataclass(frozen=True)
class GraphSnapshot:
    version: int
    graph_data: Any
    graph: Any
    created_at: datetime

    @classmethod
    def create(cls, version: int, graph_data: Any, graph: Any):
        return cls(version, graph_data, graph, datetime.now(timezone.utc))


class GraphSyncManager:
    """Explicit post-commit bridge; future outbox consumers call the same method."""

    def __init__(self, repository: GraphRepository, recommender: "GraphRecommender"):
        self.repository = repository
        self.recommender = recommender

    async def sync_after_commit(self, changes: Iterable[GraphChange]) -> GraphSnapshot:
        changes = list(changes)
        deleted = [
            EmbeddingKey(change.entity_type, change.entity_id)
            for change in changes
            if change.operation == "delete"
            and change.entity_type in {"learner", "resource", "knowledge_point"}
            and change.entity_id is not None
        ]
        if deleted:
            await self.repository.delete_embeddings(deleted)
        return await self.recommender.refresh_full(changes=changes)


def _device(value: str) -> torch.device:
    if value == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(value)


class GraphRecommender:
    """Inference-only service. It never mutates learned weights online."""

    def __init__(
        self,
        repository: GraphRepository,
        embedding_provider: EmbeddingProvider,
        checkpoint_dir: str | Path,
        *,
        device: str = "auto",
        template_version: str = TEXT_TEMPLATE_VERSION,
    ):
        self.repository = repository
        self.embedding_provider = embedding_provider
        self.checkpoint_dir = Path(checkpoint_dir)
        self.device = _device(device)
        self.template_version = template_version
        self._builder = GraphBuilder()
        self._resolver = EmbeddingResolver(
            repository, embedding_provider, template_version=template_version
        )
        self._snapshot: GraphSnapshot | None = None
        self._encoder = None
        self._resource_scorer = None
        self._peer_scorer = None
        self._model_config: GraphModelConfig | None = None
        self._refresh_lock = asyncio.Lock()
        self.sync_manager = GraphSyncManager(repository, self)

    async def start(self) -> GraphSnapshot:
        """Load checkpoints, construct the graph, then publish version one."""
        async with self._refresh_lock:
            self._model_config = GraphModelConfig.load(self.checkpoint_dir)
            graph_data = await self._load_graph_data(
                self._model_config.embedding_dim,
                verify_embedding_cache=False,
            )
            graph = graph_data.to_heterodata().to(self.device)
            self._encoder, self._resource_scorer, self._peer_scorer = load_checkpoints(
                self.checkpoint_dir,
                graph=graph,
                device=self.device,
                model_config=self._model_config,
            )
            snapshot = GraphSnapshot.create(1, graph_data, graph)
            self._snapshot = snapshot
            return snapshot

    async def refresh_full(
        self,
        *,
        changes: Iterable[GraphChange] | None = None,
    ) -> GraphSnapshot:
        """Build a new graph structure before atomically publishing it."""
        async with self._refresh_lock:
            if self._encoder is None:
                raise RuntimeError("GraphRecommender.start() must complete before refresh_full()")
            assert self._model_config is not None
            force_keys, verify_embedding_cache = self._embedding_refresh_plan(changes)
            graph_data = await self._load_graph_data(
                self._model_config.embedding_dim,
                verify_embedding_cache=verify_embedding_cache,
                force_embedding_keys=force_keys,
            )
            graph = graph_data.to_heterodata().to(self.device)
            current_version = self._snapshot.version if self._snapshot else 0
            snapshot = GraphSnapshot.create(current_version + 1, graph_data, graph)
            self._snapshot = snapshot
            return snapshot

    async def sync_after_commit(self, changes: Iterable[GraphChange]) -> GraphSnapshot:
        return await self.sync_manager.sync_after_commit(changes)

    async def reload_model(self, checkpoint_dir: str | Path | None = None) -> GraphSnapshot:
        """Load replacement checkpoints and publish a fresh graph structure."""
        if checkpoint_dir is not None:
            self.checkpoint_dir = Path(checkpoint_dir)
        async with self._refresh_lock:
            self._model_config = GraphModelConfig.load(self.checkpoint_dir)
            graph_data = await self._load_graph_data(
                self._model_config.embedding_dim,
                verify_embedding_cache=False,
            )
            graph = graph_data.to_heterodata().to(self.device)
            self._encoder, self._resource_scorer, self._peer_scorer = load_checkpoints(
                self.checkpoint_dir,
                graph=graph,
                device=self.device,
                model_config=self._model_config,
            )
            current_version = self._snapshot.version if self._snapshot else 0
            snapshot = GraphSnapshot.create(current_version + 1, graph_data, graph)
            self._snapshot = snapshot
            return snapshot

    def rank_resources(
        self,
        learner_id: str,
        candidate_resource_ids: Sequence[str],
        k: int,
        *,
        history_resource_ids: Sequence[str] | None = None,
    ) -> list[RankedItem]:
        snapshot = self._require_snapshot()
        graph_data = snapshot.graph_data
        learner_index = graph_data.id_to_index["learner"].get(learner_id)
        if learner_index is None:
            raise KeyError(f"unknown learner: {learner_id}")
        candidate_indexes = [
            graph_data.id_to_index["resource"][resource_id]
            for resource_id in dict.fromkeys(candidate_resource_ids)
            if resource_id in graph_data.id_to_index["resource"]
        ]
        if not candidate_indexes or k <= 0:
            return []
        graph = (
            self._graph_with_resource_history(snapshot, learner_id, history_resource_ids)
            if history_resource_ids
            else snapshot.graph
        )
        encoded_nodes = self._forward_graph(graph)
        candidates = encoded_nodes["resource"][candidate_indexes]
        learner = encoded_nodes["learner"][learner_index].unsqueeze(0).expand(candidates.size(0), -1)
        with torch.no_grad():
            scores = torch.sigmoid(self._resource_scorer(learner, candidates).view(-1))
        return self._top_k(graph_data.node_ids["resource"], candidate_indexes, scores, k)

    @staticmethod
    def _graph_with_resource_history(
        snapshot: GraphSnapshot,
        learner_id: str,
        history_resource_ids: Sequence[str],
    ) -> Any:
        """Replace one learner's resource edges on a request-local graph copy."""
        graph_data = snapshot.graph_data
        learner_index = graph_data.id_to_index["learner"].get(learner_id)
        if learner_index is None:
            raise KeyError(f"unknown learner: {learner_id}")

        resource_indexes = graph_data.id_to_index["resource"]
        resource_indexes = [
            resource_indexes[resource_id]
            for resource_id in dict.fromkeys(history_resource_ids)
            if resource_id in resource_indexes
        ]
        graph = snapshot.graph.clone()
        relations = (
            (("learner", "interacted_with", "resource"), 0, learner_index, resource_indexes),
            (("resource", "rev_interacted_with", "learner"), 1, learner_index, resource_indexes),
        )
        for relation, learner_dimension, learner_value, resource_values in relations:
            edge_index = graph[relation].edge_index
            retained_edges = edge_index[:, edge_index[learner_dimension] != learner_value]
            if resource_values:
                if learner_dimension == 0:
                    replacement_edges = torch.tensor(
                        [[learner_value] * len(resource_values), resource_values],
                        dtype=edge_index.dtype,
                        device=edge_index.device,
                    )
                else:
                    replacement_edges = torch.tensor(
                        [resource_values, [learner_value] * len(resource_values)],
                        dtype=edge_index.dtype,
                        device=edge_index.device,
                    )
                retained_edges = torch.cat((retained_edges, replacement_edges), dim=1)
            graph[relation].edge_index = retained_edges
        return graph

    def rank_peers(
        self,
        learner_id: str,
        candidate_learner_ids: Sequence[str],
        k: int,
        *,
        include_existing_partners: bool = False,
        history_partner_ids: Sequence[str] | None = None,
    ) -> list[RankedItem]:
        snapshot = self._require_snapshot()
        graph_data = snapshot.graph_data
        learner_index = graph_data.id_to_index["learner"].get(learner_id)
        if learner_index is None:
            raise KeyError(f"unknown learner: {learner_id}")
        partners = graph_data.partners.get(learner_id, set())
        candidate_indexes = [
            graph_data.id_to_index["learner"][candidate_id]
            for candidate_id in dict.fromkeys(candidate_learner_ids)
            if candidate_id in graph_data.id_to_index["learner"]
            and candidate_id != learner_id
            and (include_existing_partners or candidate_id not in partners)
        ]
        if not candidate_indexes or k <= 0:
            return []
        graph = (
            self._graph_with_partner_history(snapshot, learner_id, history_partner_ids)
            if history_partner_ids
            else snapshot.graph
        )
        encoded_nodes = self._forward_graph(graph)
        candidates = encoded_nodes["learner"][candidate_indexes]
        learner = encoded_nodes["learner"][learner_index].unsqueeze(0).expand(candidates.size(0), -1)
        with torch.no_grad():
            scores = torch.sigmoid(symmetric_logits(self._peer_scorer, learner, candidates).view(-1))
        return self._top_k(graph_data.node_ids["learner"], candidate_indexes, scores, k)

    @staticmethod
    def _graph_with_partner_history(
        snapshot: GraphSnapshot,
        learner_id: str,
        history_partner_ids: Sequence[str],
    ) -> Any:
        """Replace one learner's partner edges on a request-local graph copy."""
        graph_data = snapshot.graph_data
        learner_index = graph_data.id_to_index["learner"].get(learner_id)
        if learner_index is None:
            raise KeyError(f"unknown learner: {learner_id}")

        learner_indexes = graph_data.id_to_index["learner"]
        partner_indexes = [
            learner_indexes[partner_id]
            for partner_id in dict.fromkeys(history_partner_ids)
            if partner_id in learner_indexes and partner_id != learner_id
        ]
        graph = snapshot.graph.clone()
        relation = ("learner", "partnered_with", "learner")
        edge_index = graph[relation].edge_index
        retained_edges = edge_index[
            :,
            (edge_index[0] != learner_index) & (edge_index[1] != learner_index),
        ]
        if partner_indexes:
            replacement_edges = torch.tensor(
                [
                    [learner_index] * len(partner_indexes) + partner_indexes,
                    partner_indexes + [learner_index] * len(partner_indexes),
                ],
                dtype=edge_index.dtype,
                device=edge_index.device,
            )
            retained_edges = torch.cat((retained_edges, replacement_edges), dim=1)
        graph[relation].edge_index = retained_edges
        return graph

    def similar_peers(
        self,
        learner_id: str,
        candidate_learner_ids: Sequence[str],
        k: int,
        *,
        include_existing_partners: bool = False,
        history_partner_ids: Sequence[str] | None = None,
    ) -> list[RankedItem]:
        """Rank peers by cosine similarity of GAT-aggregated learner embeddings."""
        snapshot = self._require_snapshot()
        graph_data = snapshot.graph_data
        learner_index = graph_data.id_to_index["learner"].get(learner_id)
        if learner_index is None:
            raise KeyError(f"unknown learner: {learner_id}")
        partners = graph_data.partners.get(learner_id, set())
        candidate_indexes = [
            graph_data.id_to_index["learner"][candidate_id]
            for candidate_id in dict.fromkeys(candidate_learner_ids)
            if candidate_id in graph_data.id_to_index["learner"]
            and candidate_id != learner_id
            and (include_existing_partners or candidate_id not in partners)
        ]
        graph = (
            self._graph_with_partner_history(snapshot, learner_id, history_partner_ids)
            if history_partner_ids
            else snapshot.graph
        )
        encoded_nodes = self._forward_graph(graph)
        return self._cosine_top_k(
            graph_data.node_ids["learner"],
            candidate_indexes,
            encoded_nodes["learner"][learner_index],
            encoded_nodes["learner"],
            k,
        )

    def rank_resource_similarity_pairs(
        self,
        reference_resource_ids: Sequence[str],
        k: int,
    ) -> list[ResourceSimilarityPair]:
        """Return independently ranked reference-resource text similarity pairs."""
        snapshot = self._require_snapshot()
        graph_data = snapshot.graph_data
        resource_indexes = graph_data.id_to_index["resource"]
        reference_ids = [
            resource_id
            for resource_id in dict.fromkeys(reference_resource_ids)
            if resource_id in resource_indexes
        ]
        if not reference_ids or k <= 0:
            return []
        reference_set = set(reference_ids)
        candidate_indexes = [index for resource_id, index in resource_indexes.items() if resource_id not in reference_set]
        if not candidate_indexes:
            return []
        text_embeddings = graph_data.node_features["resource"]
        with torch.no_grad():
            references = F.normalize(
                text_embeddings[[resource_indexes[resource_id] for resource_id in reference_ids]],
                dim=-1,
            )
            candidates = F.normalize(text_embeddings[candidate_indexes], dim=-1)
            pair_scores = (candidates @ references.T).reshape(-1)
            limit = min(k, pair_scores.numel())
            values, positions = torch.topk(pair_scores, k=limit)
        reference_count = len(reference_ids)
        return [
            ResourceSimilarityPair(
                id=graph_data.node_ids["resource"][candidate_indexes[int(position) // reference_count]],
                reference_id=reference_ids[int(position) % reference_count],
                score=float(value),
            )
            for value, position in zip(values.cpu().tolist(), positions.cpu().tolist(), strict=True)
        ]

    def get_status(self) -> dict[str, object]:
        if self._snapshot is None:
            return {"ready": False, "version": 0}
        graph_data = self._snapshot.graph_data
        return {
            "ready": True,
            "version": self._snapshot.version,
            "created_at": self._snapshot.created_at.isoformat(),
            "embedding_model_id": self.embedding_provider.model_id,
            "embedding_dimension": self._model_config.embedding_dim,
            "nodes": {node_type: len(ids) for node_type, ids in graph_data.node_ids.items()},
            "edges": {
                "|".join(relation): int(edge_index.size(1))
                for relation, edge_index in graph_data.edge_index.items()
            },
        }

    @staticmethod
    def _embedding_refresh_plan(
        changes: Iterable[GraphChange] | None,
    ) -> tuple[set[EmbeddingKey], bool]:
        if changes is None:
            return set(), True
        force_keys: set[EmbeddingKey] = set()
        for change in changes:
            if change.entity_type == "knowledge_point":
                # Knowledge-point text is included in resource and learner templates.
                return set(), True
            if (
                change.operation == "upsert"
                and change.entity_type in {"learner", "resource"}
                and change.entity_id is not None
            ):
                force_keys.add(EmbeddingKey(change.entity_type, change.entity_id))
            elif change.entity_type == "edge" and change.relation_type == "covers" and change.source_id:
                force_keys.add(EmbeddingKey("resource", change.source_id))
            elif (
                change.entity_type == "edge"
                and change.relation_type == "has_knowledge_state"
                and change.source_id
            ):
                force_keys.add(EmbeddingKey("learner", change.source_id))
            elif change.entity_type == "edge" and change.relation_type == "precedes" and change.target_id:
                force_keys.add(EmbeddingKey("knowledge_point", change.target_id))
        return force_keys, False

    async def _load_graph_data(
        self,
        embedding_dimension: int,
        *,
        verify_embedding_cache: bool,
        force_embedding_keys: Iterable[EmbeddingKey] = (),
    ):
        rows = await self.repository.load_rows()
        embeddings = await self._resolver.resolve(
            rows,
            embedding_dimension=embedding_dimension,
            verify_cache=verify_embedding_cache,
            force_keys=force_embedding_keys,
        )
        return self._builder.build(
            rows,
            embeddings,
            embedding_dimension=embedding_dimension,
        )

    def _forward_graph(self, graph: Any) -> dict[str, torch.Tensor]:
        """Run full-graph GAT inference for one ranking or similarity request."""
        with torch.no_grad():
            return {node_type: values.detach() for node_type, values in self._encoder(graph).items()}

    def _require_snapshot(self) -> GraphSnapshot:
        if self._snapshot is None or self._resource_scorer is None or self._peer_scorer is None:
            raise RuntimeError("GraphRecommender.start() must complete before ranking")
        return self._snapshot

    @staticmethod
    def _top_k(
        ids: list[str], candidate_indexes: list[int], scores: torch.Tensor, k: int
    ) -> list[RankedItem]:
        limit = min(k, len(candidate_indexes))
        values, positions = torch.topk(scores, k=limit)
        return [
            RankedItem(id=ids[candidate_indexes[position]], score=float(value))
            for value, position in zip(values.cpu().tolist(), positions.cpu().tolist(), strict=True)
        ]

    @classmethod
    def _cosine_top_k(
        cls,
        ids: list[str],
        candidate_indexes: list[int],
        anchor: torch.Tensor,
        encoded_candidates: torch.Tensor,
        k: int,
    ) -> list[RankedItem]:
        if not candidate_indexes or k <= 0:
            return []
        with torch.no_grad():
            scores = F.cosine_similarity(
                encoded_candidates[candidate_indexes],
                anchor.unsqueeze(0),
                dim=-1,
            )
        return cls._top_k(ids, candidate_indexes, scores, k)
