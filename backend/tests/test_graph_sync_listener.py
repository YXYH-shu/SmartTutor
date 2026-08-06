"""Tests for translating committed ORM graph changes into runtime refreshes."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.database import (
    _GRAPH_CHANGES_KEY,
    _collect_graph_changes,
    _sync_graph_changes,
)
from algorithm.graph_recommender.data.types import GraphChange
from app.models.learner_interaction import LearnerResourceInteraction
from app.models.user_profile import UserProfile


class _Session:
    def __init__(self, *, new=(), dirty=(), deleted=()) -> None:
        self.info: dict[str, list[GraphChange]] = {}
        self.new = tuple(new)
        self.dirty = tuple(dirty)
        self.deleted = tuple(deleted)

    @staticmethod
    def is_modified(_instance, *, include_collections: bool) -> bool:
        assert include_collections is False
        return True


def test_graph_change_listener_collects_node_and_interaction_updates():
    session = _Session(
        new=(
            UserProfile(user_id="learner-1"),
            LearnerResourceInteraction(learner_id="learner-1", resource_id="resource-1"),
        )
    )

    _collect_graph_changes(session, None)

    assert session.info[_GRAPH_CHANGES_KEY] == [
        GraphChange("upsert", "learner", entity_id="learner-1"),
        GraphChange(
            "upsert",
            "edge",
            relation_type="interacted_with",
            source_id="learner-1",
            target_id="resource-1",
        ),
    ]


@pytest.mark.asyncio
async def test_graph_change_listener_refreshes_after_commit(monkeypatch):
    change = GraphChange(
        "upsert",
        "edge",
        relation_type="interacted_with",
        source_id="learner-1",
        target_id="resource-1",
    )
    sync = AsyncMock()
    monkeypatch.setattr("app.database._run_graph_sync", sync)

    await _sync_graph_changes([change])

    sync.assert_awaited_once_with([change])
