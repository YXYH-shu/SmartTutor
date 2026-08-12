import importlib

import pytest

decision_node_module = importlib.import_module("app.graph.nodes.decision_node")
from app.graph.nodes.stage_executor import (
    _profile_with_diagnosis,
    _resolve_agent_names,
)


class FakeEngine:
    default_workflow = "adaptive_learning"
    workflows = {
        "workflows": {
            "onboarding": {
                "stages": [
                    {
                        "id": "welcome",
                        "agents": ["knowledge_responder"],
                    },
                    {
                        "id": "diagnosis_and_plan",
                        "agents": [
                            "cognitive_diagnosis",
                            "learning_path",
                            "knowledge_responder",
                        ],
                    },
                ]
            },
            "adaptive_learning": {
                "stages": [
                    {
                        "id": "teaching",
                        "agents": [
                            "cognitive_diagnosis",
                            "resource_recommender",
                            "knowledge_responder",
                        ],
                    }
                ]
            },
        }
    }

    def __init__(self, decision):
        self.decision = decision

    async def decide_next_step(self, state, agents_meta):
        return self.decision

    def get_stage(self, workflow, stage_id):
        for stage in self.workflows["workflows"][workflow]["stages"]:
            if stage["id"] == stage_id:
                return stage
        return None

    def get_first_stage(self, workflow):
        return self.workflows["workflows"][workflow]["stages"][0]


def _state():
    return {
        "workflow_type": "adaptive_learning",
        "current_stage": "teaching",
        "pre_focus": [],
        "context": {},
    }


@pytest.mark.asyncio
async def test_path_request_preserves_learning_path_sequence_on_stage_switch(monkeypatch):
    engine = FakeEngine(
        {
            "decision": "switch_stage",
            "target_workflow": "adaptive_learning",
            "target_stage": "teaching",
            "agent_sequence": [
                "cognitive_diagnosis",
                "learning_path",
                "knowledge_responder",
            ],
            "focus_agents": ["learning_path"],
        }
    )
    monkeypatch.setattr(decision_node_module, "_get_engine", lambda: engine)
    monkeypatch.setattr(decision_node_module, "list_agents", lambda: [])

    result = await decision_node_module.decision_node(_state())

    assert result["next_agents"] == [
        "cognitive_diagnosis",
        "learning_path",
        "knowledge_responder",
    ]


@pytest.mark.asyncio
async def test_invalid_stage_name_resolves_stage_matching_path_sequence(monkeypatch):
    engine = FakeEngine(
        {
            "decision": "switch_stage",
            "target_workflow": "onboarding",
            "target_stage": "diagnosis_planning",
            "agent_sequence": [
                "cognitive_diagnosis",
                "learning_path",
                "knowledge_responder",
            ],
            "focus_agents": ["learning_path"],
        }
    )
    monkeypatch.setattr(decision_node_module, "_get_engine", lambda: engine)
    monkeypatch.setattr(decision_node_module, "list_agents", lambda: [])

    result = await decision_node_module.decision_node(_state())

    assert result["current_stage"] == "diagnosis_and_plan"
    assert result["workflow_type"] == "onboarding"
    assert "learning_path" in result["next_agents"]


def test_stage_executor_keeps_explicit_learning_path_queue():
    stage = {
        "agents": [
            "cognitive_diagnosis",
            "resource_recommender",
            "knowledge_responder",
        ]
    }
    state = {
        "next_agents": [
            "cognitive_diagnosis",
            "learning_path",
            "knowledge_responder",
        ]
    }

    assert _resolve_agent_names(stage, state) == state["next_agents"]


def test_profile_refresh_keeps_only_current_diagnosis_states():
    previous_profile = {
        "current_level": "初级",
        "knowledge_graph": {
            **{str(index): 0.1 for index in range(1, 335)},
            "_graph": {"old": True},
        },
        "weak_points": [{"skill_id": "old"}],
    }
    diagnosis = {
        "knowledge_states": [
            {"skill_id": str(index), "mastery_rate": 0.25}
            for index in range(101, 119)
        ],
        "weak_points": [{"skill_id": "101"}],
        "knowledge_graph": {"nodes": [{"id": "101"}]},
    }

    refreshed = _profile_with_diagnosis(previous_profile, diagnosis)

    assert refreshed["current_level"] == "初级"
    assert set(refreshed["knowledge_graph"]) == {
        *map(str, range(101, 119)),
        "_graph",
    }
    assert refreshed["knowledge_graph"]["101"] == 0.25
    assert refreshed["weak_points"] == [{"skill_id": "101"}]
