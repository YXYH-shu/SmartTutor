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

        plan_response = {
            "need_tool": True,
            "target_knowledge": ["Python函数"],
            "target_count": 1,
            "recall_strategy": "按知识点召回后排序",
            "ranking_criteria": ["personality"],
            "tool_calls": [
                {
                    "tool_name": "SqlRetrievalTool",
                    "input": {"sql": "SELECT id FROM learning_resources WHERE name LIKE '%Python函数%'"},
                },
                {
                    "tool_name": "RankingTool",
                    "input": {"schema": "personality", "num": 1},
                }
            ],
        }
        reflection_response = {
            "passed": True,
            "issues": [],
            "suggestion": "",
            "coverage_score": 0.8,
            "difficulty_match": 0.8,
            "diversity_score": 0.8,
        }
        summary_response = {
            "recommendation_text": "已完成 Python 函数资源推荐流程。",
            "planning": {
                "recall_strategy": "按知识点召回后排序",
                "ranking_criteria": ["personality"],
                "target_count": 1,
            },
            "resources": [],
            "rationale": "根据计划调用工具后汇总。",
            "sequence": [],
            "reflection": {
                "coverage_score": 0.8,
                "difficulty_match": 0.8,
                "diversity_score": 0.8,
                "improvement_suggestion": "",
            },
            "tool_trace": [],
        }
        _patch_llm.chat_completion = AsyncMock(
            side_effect=[
                _mock_llm_response(plan_response),
                _mock_llm_response(reflection_response),
                _mock_llm_response(summary_response),
            ]
        )

        agent = ResourceRecommenderAgent(llm=_patch_llm)
        agent._run_select_sql = AsyncMock(return_value=[{"id": "res-1"}])
        agent._fetch_resource_details = AsyncMock(
            return_value={
                "res-1": {
                    "id": "res-1",
                    "name": "Python 函数入门视频",
                    "type": "video",
                    "url": "https://example.com/python-functions",
                    "difficult": 0.3,
                    "time_need": 15,
                    "knowledge_tags": ["Python函数"],
                }
            }
        )
        result = await agent.execute(
            {"target_knowledge": "Python函数", "difficulty": "初级", "learning_style": "视觉"},
            context={"conversation_id": "conv-6"},
        )
        assert result["output"]["planning"]["target_count"] == 1
        assert result["output"]["tool_trace"][0]["tool"] == "SqlRetrievalTool"
        assert result["output"]["tool_trace"][1]["tool"] == "RankingTool"
        assert result["output"]["response_text"] == result["output"]["recommendation_text"]
        assert result["output"]["content"] == result["output"]["recommendation_text"]
        assert result["output"]["raw_response"] == result["output"]["recommendation_text"]
        assert result["output"]["final_response"] == result["output"]["recommendation_text"]
        assert result["output"]["resource_list"]["resources"] == result["output"]["resources"]
        assert "query_results" in result["output"]["resource_list"]
        assert _patch_llm.chat_completion.call_count == 3

    @pytest.mark.asyncio
    async def test_persists_recommendation_after_summary(self, _patch_llm):
        from app.services.agents.resource_recommender import ResourceRecommenderAgent

        class DummyAsyncSession:
            def __init__(self):
                self.added = []
                self.committed = False

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            def add(self, item):
                self.added.append(item)

            async def commit(self):
                self.committed = True

        plan_response = {
            "need_tool": False,
            "question": "recommend one resource",
            "final_answer": "",
            "target_knowledge": ["photosynthesis"],
            "target_count": 1,
        }
        summary_response = {
            "recommendation_text": "Try the photosynthesis intro video.",
            "planning": {
                "recall_strategy": "summary resource",
                "ranking_criteria": ["personality"],
                "target_count": 1,
            },
            "resources": [
                {
                    "id": "res-1",
                    "type": "video",
                    "title": "Photosynthesis Intro",
                    "url": "https://example.com/photosynthesis",
                    "difficulty": "beginner",
                    "time_needed_min": 12,
                    "knowledge_tags": ["photosynthesis"],
                    "recommend_reason": "Matches the current question.",
                }
            ],
            "rationale": "A short beginner video fits the request.",
            "sequence": ["Watch Photosynthesis Intro"],
            "reflection": {
                "coverage_score": 0.9,
                "difficulty_match": 0.9,
                "diversity_score": 0.8,
                "improvement_suggestion": "",
            },
            "tool_trace": [{"tool": "SummaryOnly", "status": "skipped"}],
        }
        _patch_llm.chat_completion = AsyncMock(
            side_effect=[
                _mock_llm_response(plan_response),
                _mock_llm_response(summary_response),
            ]
        )

        dummy_session = DummyAsyncSession()
        agent = ResourceRecommenderAgent(llm=_patch_llm)
        agent.enrich_input = AsyncMock(side_effect=lambda data, context: data)
        agent._log_execution = AsyncMock()
        agent.post_process = AsyncMock()

        with patch("app.database.AsyncSessionLocal", return_value=dummy_session):
            result = await agent.execute(
                {
                    "user_id": "user-1",
                    "conversation_id": "conv-input",
                    "current_message": "Please recommend a photosynthesis video.",
                    "target_knowledge": ["photosynthesis"],
                },
                context={"conversation_id": "conv-ctx", "user_id": "user-1"},
            )

        assert dummy_session.committed is True
        assert len(dummy_session.added) == 1

        record = dummy_session.added[0]
        assert record.learner_id == "user-1"
        assert record.session_id == "conv-ctx"
        assert record.rec_num == 1
        assert record.rec_resources["resources"][0]["id"] == "res-1"
        assert result["output"]["recommendation_id"] == record.id
        assert result["output"]["resource_list"]["recommendation_id"] == record.id

    @pytest.mark.asyncio
    async def test_query_tool_executes_readonly_sql(self, _patch_llm):
        from app.services.agents.resource_recommender import ResourceRecommenderAgent

        agent = ResourceRecommenderAgent(llm=_patch_llm)
        agent._run_select_sql = AsyncMock(return_value=[{"total": 2}])

        result = await agent._query_tool(
            {"sql": "SELECT COUNT(*) AS total FROM learning_resources"},
            {},
        )

        assert result == [{"total": 2}]
        agent._run_select_sql.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sql_retrieval_tool_returns_resource_candidates(self, _patch_llm):
        from app.services.agents.resource_recommender import ResourceRecommenderAgent

        agent = ResourceRecommenderAgent(llm=_patch_llm)
        agent._run_select_sql = AsyncMock(return_value=[{"id": "res-1"}])
        agent._fetch_resource_details = AsyncMock(
            return_value={
                "res-1": {
                    "id": "res-1",
                    "name": "Python 函数入门视频",
                    "type": "video",
                    "url": "https://example.com/python-functions",
                    "difficult": 0.3,
                    "time_need": 15,
                    "knowledge_tags": ["Python函数"],
                }
            }
        )

        result = await agent._sql_retrieval_tool(
            {"sql": "SELECT id FROM learning_resources WHERE type LIKE '%video%'"},
            {},
        )

        assert result[0]["id"] == "res-1"
        assert result[0]["title"] == "Python 函数入门视频"
        assert result[0]["difficulty"] == "初级"

    @pytest.mark.asyncio
    async def test_ranking_tool_sorts_and_limits(self, _patch_llm):
        from app.services.agents.resource_recommender import ResourceRecommenderAgent

        agent = ResourceRecommenderAgent(llm=_patch_llm)
        agent._predict_ctr_scores = AsyncMock(return_value=[0.99, 0.01, 0.5])
        candidates = [
            {"id": "slow", "title": "慢资源", "time_needed_min": 45},
            {"id": "fast", "title": "快资源", "time_needed_min": 10},
            {"id": "medium", "title": "中等资源", "time_needed_min": 20},
        ]

        result = await agent._ranking_tool(
            {"schema": "time_need", "num": 2},
            candidates,
            {},
        )

        assert [item["id"] for item in result] == ["fast", "medium"]
        agent._predict_ctr_scores.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_personality_ranking_uses_ctr_scores(self, _patch_llm):
        from app.services.agents.resource_recommender import ResourceRecommenderAgent

        agent = ResourceRecommenderAgent(llm=_patch_llm)
        agent._predict_ctr_scores = AsyncMock(return_value=[0.2, 0.9, 0.5])
        candidates = [
            {"id": "a", "title": "A"},
            {"id": "b", "title": "B"},
            {"id": "c", "title": "C"},
        ]

        result = await agent._ranking_tool(
            {"schema": "personality", "num": 2},
            candidates,
            {},
        )

        assert [item["id"] for item in result] == ["b", "c"]
        assert result[0]["ctr_score"] == 0.9
        agent._predict_ctr_scores.assert_awaited_once()

    def test_resource_ranking_predictor_matches_algorithm_input_shape(self):
        from app.services.resource_ranking_predictor import ResourceRankingPredictor

        predictor = ResourceRankingPredictor(config={"enabled": False})
        user_fids = {fid for fid, _, _ in predictor.schema["user_int"].entries}

        assert not {200, 201, 202, 203} & user_fids

        batch = predictor.pack_instances(
            [
                {
                    "user_features": {"user_id": 1, "current_level": 2},
                    "item_features": {"resource_id": "res-uuid", "resource_type": "video"},
                    "sequence_features": {"interaction": {}},
                    "context_features": {},
                }
            ]
        )

        item_id_offset, _ = predictor.schema["item_int"].offset_length(101)
        item_id_vocab = predictor.schema["item_int"].vocab_at(item_id_offset)
        assert "cross_dense_feats" not in batch
        assert len(batch["user_int_feats"][0]) == predictor.schema["user_int"].total_dim
        assert len(batch["user_dense_feats"][0]) == predictor.schema["user_dense"].total_dim
        assert 0 < batch["item_int_feats"][0][item_id_offset] < item_id_vocab

    @pytest.mark.asyncio
    async def test_reflection_rejects_insufficient_recommendations(self, _patch_llm):
        from app.services.agents.resource_recommender import ResourceRecommenderAgent

        _patch_llm.chat_completion = AsyncMock(
            return_value=_mock_llm_response(
                {
                    "passed": True,
                    "issues": [],
                    "suggestion": "",
                    "coverage_score": 1,
                    "difficulty_match": 1,
                    "diversity_score": 1,
                }
            )
        )
        agent = ResourceRecommenderAgent(llm=_patch_llm)

        reflection, _ = await agent._reflection(
            plan={
                "need_tool": True,
                "target_count": 2,
                "tool_calls": [
                    {"tool_name": "SqlRetrievalTool", "input": {"sql": "SELECT id FROM learning_resources"}},
                    {"tool_name": "RankingTool", "input": {"schema": "personality", "num": 2}},
                ],
            },
            tool_results={
                "ranked_resources": [{"id": "res-1", "title": "资源1"}],
                "tool_trace": [],
            },
            input_data={"current_message": "推荐两个资源", "recent_messages": []},
        )

        assert reflection["passed"] is False
        assert "目标 2 个，当前仅 1 个" in reflection["issues"][0]


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
