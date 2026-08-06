from __future__ import annotations

import asyncio
import importlib

import pytest
from langchain_core.messages import HumanMessage

stage_module = importlib.import_module("app.graph.nodes.stage_executor")


class StubEngine:
    default_workflow = "adaptive_learning"
    workflows = {"workflows": {}}

    def get_stage(self, workflow: str, stage_id: str):
        return {
            "id": "teaching",
            "agents": [
                "cognitive_diagnosis",
                "resource_recommender",
                "knowledge_responder",
            ],
            "output_to_user": True,
        }

    def get_first_stage(self, workflow: str):
        return self.get_stage(workflow, "teaching")

    def get_next_stage(self, workflow: str, stage_id: str):
        return None


class ImmediateAgent:
    def __init__(self, output: dict):
        self.output = output

    async def execute(self, *, input_data, context):
        return {"output": self.output, "latency_ms": 1}


class CapturingAgent(ImmediateAgent):
    def __init__(self, output: dict):
        super().__init__(output)
        self.input_data = None

    async def execute(self, *, input_data, context):
        self.input_data = input_data
        return await super().execute(input_data=input_data, context=context)


class HangingAgent:
    async def execute(self, *, input_data, context):
        await asyncio.sleep(60)
        raise AssertionError("unreachable")


@pytest.mark.asyncio
async def test_stage_timeout_skips_hanging_agent_and_still_returns_response(monkeypatch):
    agents = {
        "cognitive_diagnosis": ImmediateAgent(
            {"topic_analysis": "这是关于电击风险的物理知识。"}
        ),
        "resource_recommender": HangingAgent(),
        "knowledge_responder": ImmediateAgent(
            {
                "response_text": "电击会使电流通过生物组织，并可能影响神经和肌肉活动。",
                "topic_tags": ["电击", "生物学影响"],
                "confidence": 0.9,
            }
        ),
    }
    monkeypatch.setattr(stage_module, "_get_engine", lambda: StubEngine())
    monkeypatch.setattr(stage_module, "get_agent", lambda name: agents[name])
    monkeypatch.setitem(stage_module._AGENT_TIMEOUT_SECONDS, "resource_recommender", 0.01)
    monkeypatch.setattr(stage_module, "_STAGE_TIMEOUT_SECONDS", 1.0)
    monkeypatch.setattr(stage_module, "_KNOWLEDGE_RESERVE_SECONDS", 0.5)

    result = await stage_module.stage_executor(
        {
            "user_id": "user-test",
            "conversation_id": "conversation-test",
            "messages": [HumanMessage(content="大象遭受电击有哪些生物学影响？")],
            "context": {
                "safety_context": {
                    "resolved_from_guide": True,
                    "core_topic": "大象遭受电击",
                }
            },
            "workflow_type": "adaptive_learning",
            "current_stage": "teaching",
            "stage_counter": 0,
            "user_profile": {},
        }
    )

    assert result["final_response"].startswith("电击会使电流")
    assert result["context"]["_agent_errors"]["resource_recommender"]["type"] == "timeout"
    assert result["context"]["knowledge_responder"]["confidence"] == 0.9
    assert result["decision"] == "finish"


@pytest.mark.asyncio
async def test_resolved_guide_exposes_only_safe_message_to_teaching_agents(monkeypatch):
    responder = CapturingAgent(
        {
            "response_text": "我们先比较现象，再解释背后的科学原理。",
            "confidence": 0.9,
        }
    )
    monkeypatch.setattr(stage_module, "_get_engine", lambda: StubEngine())
    monkeypatch.setattr(stage_module, "get_agent", lambda name: responder)

    result = await stage_module.stage_executor(
        {
            "user_id": "user-test",
            "conversation_id": "conversation-test",
            "messages": [
                HumanMessage(content="原始风险请求"),
                HumanMessage(content="能量变化会产生哪些现象？\n选定学习方向：能量转化"),
            ],
            "context": {
                "safety_context": {
                    "resolved_from_guide": True,
                    "safe_query": "能量变化会产生哪些现象？",
                    "selected_option": "能量转化",
                }
            },
            "workflow_type": "adaptive_learning",
            "current_stage": "teaching",
            "stage_counter": 0,
            "user_profile": {},
        }
    )

    assert responder.input_data["current_message"].startswith("能量变化")
    assert responder.input_data["message_history"] == [
        {
            "role": "human",
            "content": "能量变化会产生哪些现象？\n选定学习方向：能量转化",
        }
    ]
    assert "原始风险请求" not in str(responder.input_data["message_history"])
    assert result["final_response"].startswith("我们先比较现象")


@pytest.mark.asyncio
async def test_resolved_guide_returns_teacher_fallback_when_all_agents_fail(monkeypatch):
    monkeypatch.setattr(stage_module, "_get_engine", lambda: StubEngine())
    monkeypatch.setattr(stage_module, "get_agent", lambda name: HangingAgent())
    monkeypatch.setattr(stage_module, "_STAGE_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(stage_module, "_KNOWLEDGE_RESERVE_SECONDS", 0.01)
    for name in stage_module._AGENT_TIMEOUT_SECONDS:
        monkeypatch.setitem(stage_module._AGENT_TIMEOUT_SECONDS, name, 0.01)

    result = await stage_module.stage_executor(
        {
            "user_id": "user-test",
            "conversation_id": "conversation-test",
            "messages": [HumanMessage(content="安全学习问题")],
            "context": {
                "safety_context": {
                    "resolved_from_guide": True,
                    "safe_query": "这个现象背后的原理是什么？",
                    "selected_option": "理解科学原理",
                }
            },
            "workflow_type": "adaptive_learning",
            "current_stage": "teaching",
            "stage_counter": 0,
            "user_profile": {},
        }
    )

    assert "理解科学原理" in result["final_response"]
    assert "📘" in result["final_response"]
    assert result["requires_user_input"] is True
