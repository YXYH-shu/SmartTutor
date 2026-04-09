"""Tests for all 8 education agents using mock LLM responses.

Run with:  pytest tests/test_agents.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure backend/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _mock_llm_response(content: dict) -> dict:
    """Build a return value that looks like LLMClient.chat_completion output."""
    return {
        "content": content,
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        "latency_ms": 150,
    }


def _mock_validate(response, schema, **kwargs):
    """Pass-through validation – returns parsed dict directly."""
    return response if isinstance(response, dict) else json.loads(response)


@pytest.fixture(autouse=True)
def _patch_llm():
    """Patch LLMClient methods for all tests so no real API calls happen."""
    with patch("app.services.agents.base_agent.LLMClient") as MockLLM, \
         patch("app.services.agents.base_agent.AsyncSessionLocal"):
        instance = MockLLM.return_value
        instance.validate_json_response = AsyncMock(side_effect=_mock_validate)
        # Default chat_completion – overridden per-test
        instance.chat_completion = AsyncMock(return_value=_mock_llm_response({}))
        yield instance


@pytest.fixture(autouse=True)
def _patch_enrich():
    """Skip DB reads in enrich_input by default."""
    with patch(
        "app.services.agents.base_agent.AsyncSessionLocal",
    ):
        yield


# ---------------------------------------------------------------------------
# Per-agent tests
# ---------------------------------------------------------------------------

class TestSafetyMonitor:
    @pytest.mark.asyncio
    async def test_safe_content(self, _patch_llm):
        from app.services.agents.safety_monitor import SafetyMonitorAgent

        expected = {
            "is_safe": True,
            "risk_level": "low",
            "transformed_text": "今天想学习什么内容？",
            "education_note": "",
        }
        _patch_llm.chat_completion = AsyncMock(return_value=_mock_llm_response(expected))
        _patch_llm.validate_json_response = AsyncMock(return_value=expected)

        agent = SafetyMonitorAgent(llm=_patch_llm)
        result = await agent.execute(
            {"raw_text": "今天想学习什么内容？", "user_age": 14},
            context={"conversation_id": "conv-1"},
        )
        assert result["agent"] == "safety_monitor"
        assert result["output"]["is_safe"] is True
        assert result["output"]["risk_level"] == "low"

    @pytest.mark.asyncio
    async def test_unsafe_content(self, _patch_llm):
        from app.services.agents.safety_monitor import SafetyMonitorAgent

        expected = {
            "is_safe": False,
            "risk_level": "high",
            "transformed_text": "如果你遇到困难，可以寻求帮助。",
            "education_note": "检测到潜在有害内容，已替换为教育引导语。",
        }
        _patch_llm.chat_completion = AsyncMock(return_value=_mock_llm_response(expected))
        _patch_llm.validate_json_response = AsyncMock(return_value=expected)

        agent = SafetyMonitorAgent(llm=_patch_llm)
        result = await agent.execute(
            {"raw_text": "我不想活了", "user_age": 14},
            context={"conversation_id": "conv-2"},
        )
        assert result["output"]["is_safe"] is False
        assert result["output"]["risk_level"] == "high"


class TestEmotionAnalyzer:
    @pytest.mark.asyncio
    async def test_detect_frustration(self, _patch_llm):
        from app.services.agents.emotion_analyzer import EmotionAnalyzerAgent

        expected = {
            "emotion": "沮丧",
            "intensity": 0.7,
            "trend": "declining",
            "learning_intent": "低，需要情感支持",
            "suggested_response_tone": "温暖鼓励，先安抚情绪",
        }
        _patch_llm.chat_completion = AsyncMock(return_value=_mock_llm_response(expected))
        _patch_llm.validate_json_response = AsyncMock(return_value=expected)

        agent = EmotionAnalyzerAgent(llm=_patch_llm)
        result = await agent.execute(
            {
                "message_history": [
                    {"role": "user", "content": "这道题我做了3遍了还是错"},
                    {"role": "assistant", "content": "再试试看"},
                    {"role": "user", "content": "我不想做了"},
                ],
                "current_message": "我太笨了，学不会",
            },
            context={"conversation_id": "conv-3"},
        )
        assert result["output"]["emotion"] == "沮丧"
        assert result["output"]["trend"] == "declining"


class TestCognitiveDiagnosis:
    @pytest.mark.asyncio
    async def test_diagnosis(self, _patch_llm):
        from app.services.agents.cognitive_diagnosis import CognitiveDiagnosisAgent

        expected = {
            "mastery_rates": {"python_basics": 0.8, "functions": 0.3},
            "weak_points": ["函数定义与调用", "参数传递"],
            "diagnosis_summary": "基础语法掌握良好，但函数部分需要加强。",
            "recommended_actions": ["复习函数定义", "完成函数练习题集"],
        }
        _patch_llm.chat_completion = AsyncMock(return_value=_mock_llm_response(expected))
        _patch_llm.validate_json_response = AsyncMock(return_value=expected)

        agent = CognitiveDiagnosisAgent(llm=_patch_llm)
        result = await agent.execute(
            {
                "recent_messages": [
                    {"role": "user", "content": "def foo(a): return a+1"},
                    {"role": "assistant", "content": "正确"},
                    {"role": "user", "content": "但lambda我不太懂"},
                ],
                "knowledge_graph": {"python_basics": 0.8},
            },
            context={"conversation_id": "conv-4"},
        )
        assert "functions" in result["output"]["mastery_rates"]
        assert len(result["output"]["weak_points"]) > 0


class TestLearningPath:
    @pytest.mark.asyncio
    async def test_generate_path(self, _patch_llm):
        from app.services.agents.learning_path import LearningPathAgent

        expected = {
            "stages": [
                {
                    "name": "基础巩固",
                    "duration_min": 30,
                    "resources": ["Python入门教程"],
                    "checkpoints": ["能独立写出简单函数"],
                }
            ],
            "estimated_completion": "约2周",
            "adaptive_rules": "根据测验结果动态调整难度",
        }
        _patch_llm.chat_completion = AsyncMock(return_value=_mock_llm_response(expected))
        _patch_llm.validate_json_response = AsyncMock(return_value=expected)

        agent = LearningPathAgent(llm=_patch_llm)
        result = await agent.execute(
            {
                "goal": "掌握Python函数",
                "current_level": "初级",
                "mastery_rates": {"python_basics": 0.6},
            },
            context={"conversation_id": "conv-5"},
        )
        assert len(result["output"]["stages"]) >= 1


class TestResourceRecommender:
    @pytest.mark.asyncio
    async def test_recommend(self, _patch_llm):
        from app.services.agents.resource_recommender import ResourceRecommenderAgent

        expected = {
            "resources": [
                {
                    "id": "r1",
                    "type": "video",
                    "title": "Python函数入门",
                    "url": "https://example.com/python-func",
                    "difficulty": "初级",
                }
            ],
            "rationale": "视频资源适合初学者建立直观理解",
            "sequence": ["先看视频", "再做练习"],
        }
        _patch_llm.chat_completion = AsyncMock(return_value=_mock_llm_response(expected))
        _patch_llm.validate_json_response = AsyncMock(return_value=expected)

        agent = ResourceRecommenderAgent(llm=_patch_llm)
        result = await agent.execute(
            {"target_knowledge": "Python函数", "difficulty": "初级", "learning_style": "视觉"},
            context={"conversation_id": "conv-6"},
        )
        assert result["output"]["resources"][0]["type"] == "video"


class TestStudyBuddy:
    @pytest.mark.asyncio
    async def test_recommend_buddy(self, _patch_llm):
        from app.services.agents.study_buddy import StudyBuddyAgent

        expected = {
            "buddies": [
                {
                    "user_id": "u-456",
                    "complement_score": 0.85,
                    "strengths": ["Python高级特性", "算法设计"],
                    "contact_suggestion": "可以一起做项目练习",
                }
            ],
            "group_suggestion": "建议组建3人小组，互补学习",
        }
        _patch_llm.chat_completion = AsyncMock(return_value=_mock_llm_response(expected))
        _patch_llm.validate_json_response = AsyncMock(return_value=expected)

        agent = StudyBuddyAgent(llm=_patch_llm)
        result = await agent.execute(
            {"topic": "Python函数", "user_graph": {"python_basics": 0.5}},
            context={"conversation_id": "conv-7"},
        )
        assert result["output"]["buddies"][0]["complement_score"] > 0.5


class TestEmpathyGenerator:
    @pytest.mark.asyncio
    async def test_generate_empathy(self, _patch_llm):
        from app.services.agents.empathy_generator import EmpathyGeneratorAgent

        expected = {
            "empathetic_response": "我理解函数确实有些难，别担心，我们一起慢慢来！",
            "psychological_techniques": ["共情", "鼓励"],
            "teacher_persona": "友善的导师",
        }
        _patch_llm.chat_completion = AsyncMock(return_value=_mock_llm_response(expected))
        _patch_llm.validate_json_response = AsyncMock(return_value=expected)

        agent = EmpathyGeneratorAgent(llm=_patch_llm)
        result = await agent.execute(
            {
                "raw_response": "函数定义格式：def function_name(params): ...",
                "emotion_state": {"emotion": "沮丧", "intensity": 0.7},
                "scenario": "知识讲解",
            },
            context={"conversation_id": "conv-8"},
        )
        assert "共情" in result["output"]["psychological_techniques"]


class TestContentPolisher:
    @pytest.mark.asyncio
    async def test_polish(self, _patch_llm):
        from app.services.agents.content_polisher import ContentPolisherAgent

        expected = {
            "polished_content": "函数是一段可重复使用的代码块。定义函数时使用 def 关键字。",
            "changes_made": ["科学术语强化", "语气软化"],
            "confidence": 0.9,
        }
        _patch_llm.chat_completion = AsyncMock(return_value=_mock_llm_response(expected))
        _patch_llm.validate_json_response = AsyncMock(return_value=expected)

        agent = ContentPolisherAgent(llm=_patch_llm)
        result = await agent.execute(
            {"content": "函数就是一堆代码放一起", "target_role": "友善的导师"},
            context={"conversation_id": "conv-9"},
        )
        assert result["output"]["confidence"] > 0.5
        assert len(result["output"]["changes_made"]) > 0


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------

class TestAgentRegistry:
    def test_list_agents(self):
        from app.services.agents import list_agents

        agents = list_agents()
        names = {a["name"] for a in agents}
        assert "safety_monitor" in names
        assert "emotion_analyzer" in names
        assert "cognitive_diagnosis" in names
        assert len(agents) == 8

    def test_get_agent(self):
        from app.services.agents import get_agent

        agent = get_agent("safety_monitor")
        assert agent.name == "safety_monitor"

    def test_get_unknown_raises(self):
        from app.services.agents import get_agent

        with pytest.raises(KeyError):
            get_agent("nonexistent_agent")
