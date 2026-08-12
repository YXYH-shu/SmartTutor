"""Heterogeneous GAT encoder with type-specific feature projections."""

from __future__ import annotations

from typing import Mapping

import torch
from torch import Tensor, nn
import torch.nn.functional as F


def _require_pyg():
    try:
        from torch_geometric.nn import GATConv, HeteroConv
    except ImportError as exc:
        raise RuntimeError(
            "torch-geometric is required for the graph recommender model."
        ) from exc
    return GATConv, HeteroConv


class HeteroGATEncoder(nn.Module):
    """Two-layer relation-aware GAT with residual self paths for cold nodes."""

    def __init__(
        self,
        metadata: tuple[list[str], list[tuple[str, str, str]]],
        in_dims: Mapping[str, int],
        *,
        hidden_dim: int = 64,
        output_dim: int = 64,
        heads: int = 2,
        num_layers: int = 2,
        dropout: float = 0.2,
    ):
        super().__init__()
        if num_layers < 1:
            raise ValueError("num_layers must be positive")
        node_types, edge_types = metadata
        GATConv, HeteroConv = _require_pyg()
        self.metadata = (list(node_types), list(edge_types))
        self.in_dims = dict(in_dims)
        self.hidden_dim = hidden_dim
        self.output_dim = output_dim
        self.heads = heads
        self.num_layers = num_layers
        self.dropout = dropout
        self.input_projection = nn.ModuleDict(
            {node_type: nn.Linear(self.in_dims[node_type], hidden_dim) for node_type in node_types}
        )
        self.convs = nn.ModuleList()
        self.residuals = nn.ModuleList()
        self.norms = nn.ModuleList()
        for layer in range(num_layers):
            input_dim = hidden_dim
            layer_output = output_dim if layer == num_layers - 1 else hidden_dim
            convs = {
                edge_type: GATConv(
                    (input_dim, input_dim),
                    layer_output,
                    heads=heads,
                    concat=False,
                    dropout=dropout,
                    add_self_loops=False,
                )
                for edge_type in edge_types
            }
            self.convs.append(HeteroConv(convs, aggr="sum"))
            self.residuals.append(
                nn.ModuleDict(
                    {
                        node_type: nn.Linear(input_dim, layer_output, bias=False)
                        for node_type in node_types
                    }
                )
            )
            if layer < num_layers - 1:
                self.norms.append(nn.ModuleDict({node_type: nn.LayerNorm(layer_output) for node_type in node_types}))

    @classmethod
    def from_graph(cls, graph, **kwargs):
        in_dims = {node_type: graph[node_type].x.size(-1) for node_type in graph.node_types}
        return cls(graph.metadata(), in_dims, **kwargs)

    def forward(self, graph) -> dict[str, Tensor]:
        x_dict = {
            node_type: F.dropout(
                F.relu(self.input_projection[node_type](graph[node_type].x)),
                p=self.dropout,
                training=self.training,
            )
            for node_type in self.metadata[0]
        }
        for layer, conv in enumerate(self.convs):
            messages = conv(x_dict, graph.edge_index_dict)
            x_dict = {
                node_type: messages.get(node_type, torch.zeros_like(self.residuals[layer][node_type](x)))
                + self.residuals[layer][node_type](x)
                for node_type, x in x_dict.items()
            }
            if layer < self.num_layers - 1:
                x_dict = {
                    node_type: F.dropout(
                        F.relu(self.norms[layer][node_type](x)),
                        p=self.dropout,
                        training=self.training,
                    )
                    for node_type, x in x_dict.items()
                }
        return x_dict


class MultiInterestHead(nn.Module):
    """Learner-only auxiliary head used during contrastive pretraining."""

    def __init__(self, dimension: int, slots: int = 4, iterations: int = 3):
        super().__init__()
        self.slots = slots
        self.iterations = iterations
        self.experts = nn.ModuleList(
            [nn.Sequential(nn.Linear(dimension, dimension), nn.ReLU(), nn.Linear(dimension, dimension)) for _ in range(slots)]
        )
        self.seed = nn.Parameter(torch.randn(slots, dimension))
        self.norm = nn.LayerNorm(dimension)

    def forward(self, learners: Tensor) -> Tensor:
        count = learners.size(0)
        expert_values = torch.stack([expert(learners) for expert in self.experts], dim=1)
        slots = self.seed.unsqueeze(0).expand(count, -1, -1).contiguous()
        for _ in range(self.iterations):
            attention = torch.einsum(
                "nkd,nkd->nk", F.normalize(slots, dim=-1), F.normalize(expert_values, dim=-1)
            )
            slots = self.norm(slots + F.softmax(attention, dim=-1).unsqueeze(-1) * expert_values)
        return slots


class Projector(nn.Module):
    def __init__(self, dimension: int):
        super().__init__()
        self.layers = nn.Sequential(nn.Linear(dimension, dimension), nn.ReLU(), nn.Linear(dimension, dimension))

    def forward(self, values: Tensor) -> Tensor:
        return F.normalize(self.layers(values), dim=-1)


class PretrainingModel(nn.Module):
    """Training-only wrapper; deployment exports its encoder state alone."""

    def __init__(self, encoder: HeteroGATEncoder, interest_slots: int = 4, interest_iterations: int = 3):
        super().__init__()
        self.encoder = encoder
        self.interest_head = MultiInterestHead(encoder.output_dim, interest_slots, interest_iterations)
        self.projector = Projector(encoder.output_dim)

    def forward(self, graph) -> dict[str, Tensor | dict[str, Tensor]]:
        embeddings = self.encoder(graph)
        return {
            "embeddings": embeddings,
            "interests": self.interest_head(embeddings["learner"]),
        }


class MLPScorer(nn.Module):
    def __init__(self, dimension: int = 64):
        super().__init__()
        self.dimension = dimension
        self.layers = nn.Sequential(
            nn.Linear(dimension * 4, dimension),
            nn.ReLU(),
            nn.Linear(dimension, 1),
        )

    def forward(self, source: Tensor, target: Tensor) -> Tensor:
        features = torch.cat([source, target, source * target, torch.abs(source - target)], dim=-1)
        return self.layers(features)


def symmetric_logits(scorer: MLPScorer, left: Tensor, right: Tensor) -> Tensor:
    """Make an order-sensitive MLP suitable for an undirected peer relation."""
    return (scorer(left, right) + scorer(right, left)) / 2
