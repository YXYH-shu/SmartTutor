"""Tests for all 8 education agents using mock LLM responses.

Run with:  pytest tests/test_agents.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
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
            "risk_detected": False,
            "risk_category": "N",
            "intent": "learning",
            "confidence": 0.99,
            "operational_request": False,
            "repeat_probe": False,
            "crisis_detected": False,
            "teachable": False,
            "risk_reason": "正常学习问题",
        }
        _patch_llm.chat_completion = AsyncMock(return_value=_mock_llm_response(expected))
        _patch_llm.validate_json_response = AsyncMock(return_value=expected)

        agent = SafetyMonitorAgent(llm=_patch_llm)
        result = await agent.execute(
            {"raw_text": "今天想学习什么内容？", "user_age": 14},
            context={"conversation_id": "conv-1"},
        )
        assert result["agent"] == "safety_monitor"
        assert result["output"]["branch"] == "PASS"

    @pytest.mark.asyncio
    async def test_unsafe_content(self, _patch_llm):
        from app.services.agents.safety_monitor import SafetyMonitorAgent

        expected = {
            "risk_detected": True,
            "risk_category": "C",
            "intent": "emotional",
            "confidence": 0.99,
            "operational_request": False,
            "repeat_probe": False,
            "crisis_detected": True,
            "teachable": False,
            "risk_reason": "检测到自伤危机信号",
        }
        _patch_llm.chat_completion = AsyncMock(return_value=_mock_llm_response(expected))
        _patch_llm.validate_json_response = AsyncMock(return_value=expected)

        agent = SafetyMonitorAgent(llm=_patch_llm)
        result = await agent.execute(
            {"raw_text": "我不想活了", "user_age": 14},
            context={"conversation_id": "conv-2"},
        )
        assert result["output"]["branch"] == "REJECT"
        assert result["output"]["reject_type"] == "CRISIS"
        assert "立即危险" in result["output"]["direct_response"]


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
    async def test_diagnosis(self, _patch_llm, monkeypatch):
        from app.config import settings
        from app.services.agents.cognitive_diagnosis import CognitiveDiagnosisAgent

        monkeypatch.setattr(settings.kt, "mode", "off")

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
    async def test_generate_path(self, _patch_llm, monkeypatch):
        from app.config import settings
        from app.services.agents.learning_path import LearningPathAgent

        monkeypatch.setattr(settings.lpp, "enabled", False)

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
    @staticmethod
    def _candidate(resource_id: str, *, title: str | None = None) -> dict[str, Any]:
        return {
            "id": resource_id,
            "title": title or resource_id,
            "type": "video",
            "url": f"https://example.com/{resource_id}",
            "difficulty": "beginner",
            "time_needed_min": 10,
            "knowledge_tags": ["physics"],
        }

    @pytest.mark.asyncio
    async def test_sql_candidates_are_graph_ranked_and_summary_keeps_execution_results(self, _patch_llm):
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
            "planning": {},
            "resources": [],
            "rationale": "根据计划调用工具后汇总。",
            "sequence": [],
            "reflection": {},
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
        agent.enrich_input = AsyncMock(side_effect=lambda data, _context: data)
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
        agent._rank_with_graph = MagicMock(
            return_value=[{"id": "res-1", "title": "Python 函数入门视频", "graph_score": 0.91}]
        )
        agent._log_execution = AsyncMock()
        agent.post_process = AsyncMock()
        result = await agent.execute(
            {
                "user_id": "learner-1",
                "current_message": "推荐一个 Python 函数资源",
                "target_knowledge": "Python函数",
                "difficulty": "初级",
                "learning_style": "视觉",
            },
            context={"persist_recommendation": False, "log_execution": False},
        )
        assert result["output"]["planning"]["target_count"] == 1
        assert result["output"]["tool_trace"][0]["tool"] == "SqlRetrievalTool"
        assert result["output"]["tool_trace"][1]["tool"] == "RankingTool"
        assert result["output"]["resources"][0]["graph_score"] == pytest.approx(0.91)
        assert result["output"]["response_text"] == result["output"]["recommendation_text"]
        assert result["output"]["content"] == result["output"]["recommendation_text"]
        assert result["output"]["raw_response"] == result["output"]["recommendation_text"]
        assert result["output"]["final_response"] == result["output"]["recommendation_text"]
        assert result["output"]["resource_list"]["resources"] == result["output"]["resources"]
        assert _patch_llm.chat_completion.call_count == 3

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
        )

        assert result[0]["id"] == "res-1"
        assert result[0]["title"] == "Python 函数入门视频"
        assert result[0]["difficulty"] == "beginner"

    @pytest.mark.asyncio
    async def test_missing_sql_uses_full_catalog_before_personality_ranking(self, _patch_llm):
        from app.services.agents.resource_recommender import ResourceRecommenderAgent

        agent = ResourceRecommenderAgent(llm=_patch_llm)
        full_catalog = [self._candidate("a"), self._candidate("b")]
        agent._load_all_resource_candidates = AsyncMock(return_value=full_catalog)
        agent._rank_with_graph = MagicMock(return_value=list(reversed(full_catalog)))
        result = await agent._execute_tools(
            {"tool_calls": [{"tool_name": "RankingTool", "input": {"schema": "personality"}}]},
            {"user_id": "learner-1"},
        )

        assert [item["id"] for item in result["ranked_resources"]] == ["b", "a"]
        assert result["tool_trace"][0] == {
            "tool": "CandidateFallback",
            "status": "applied",
            "reason": "sql_not_called",
            "count": 2,
        }
        assert result["execution_context"]["candidate_source"] == "full_catalog"

    @pytest.mark.asyncio
    async def test_empty_sql_uses_full_catalog_before_personality_ranking(self, _patch_llm):
        from app.services.agents.resource_recommender import ResourceRecommenderAgent

        agent = ResourceRecommenderAgent(llm=_patch_llm)
        full_catalog = [self._candidate("a"), self._candidate("b")]
        agent._sql_retrieval_tool = AsyncMock(return_value=[])
        agent._load_all_resource_candidates = AsyncMock(return_value=full_catalog)
        agent._rank_with_graph = MagicMock(return_value=full_catalog)
        result = await agent._execute_tools(
            {
                "tool_calls": [
                    {"tool_name": "SqlRetrievalTool", "input": {"sql": "SELECT id FROM learning_resources"}},
                    {"tool_name": "RankingTool", "input": {"schema": "personality"}},
                ]
            },
            {"user_id": "learner-1"},
        )

        assert result["tool_trace"][1]["tool"] == "CandidateFallback"
        assert result["tool_trace"][1]["reason"] == "sql_empty"
        assert result["execution_context"]["ranking"]["candidate_count"] == 2

    @pytest.mark.asyncio
    async def test_personality_ranking_number_policy_and_graph_fallback(self, _patch_llm):
        from app.services.agents.resource_recommender import ResourceRecommenderAgent

        agent = ResourceRecommenderAgent(llm=_patch_llm)
        candidates = [self._candidate(f"r-{index}") for index in range(20)]
        agent._rank_with_graph = MagicMock(return_value=candidates)

        default_ranked, _, default_metadata = await agent._ranking_tool(
            {"schema": "personality"}, candidates, {"user_id": "learner-1"}, fallback_reason="sql_empty"
        )
        capped_ranked, _, capped_metadata = await agent._ranking_tool(
            {"schema": "personality", "num": 20}, candidates, {"user_id": "learner-1"}, fallback_reason="sql_empty"
        )

        assert len(default_ranked) == 5
        assert default_metadata["effective_num"] == 5
        assert default_metadata["num_policy"] == "default"
        assert len(capped_ranked) == 15
        assert capped_metadata["effective_num"] == 15
        assert capped_metadata["num_policy"] == "capped"

        invalid_ranked, _, invalid_metadata = await agent._ranking_tool(
            {"schema": "personality", "num": 0}, candidates, {"user_id": "learner-1"}, fallback_reason="sql_empty"
        )
        assert len(invalid_ranked) == 5
        assert invalid_metadata["num_policy"] == "default_invalid"

        agent._rank_with_graph = MagicMock(return_value=None)
        fallback_ranked, _, fallback_metadata = await agent._ranking_tool(
            {"schema": "personality", "num": 2}, candidates[:2], {"user_id": "learner-1"}, fallback_reason="sql_empty"
        )
        assert [item["id"] for item in fallback_ranked] == ["r-0", "r-1"]
        assert fallback_metadata["ranking_backend"] == "deterministic_fallback"

    @pytest.mark.asyncio
    async def test_similarity_ranking_keeps_independent_multi_anchor_pairs(self, _patch_llm):
        from app.services.agents.resource_recommender import ResourceRecommenderAgent

        agent = ResourceRecommenderAgent(llm=_patch_llm)
        anchors = [self._candidate("anchor-a", title="Anchor A"), self._candidate("anchor-b", title="Anchor B")]
        agent._fetch_resource_details = AsyncMock(return_value={
            "candidate": {
                "id": "candidate",
                "name": "Candidate",
                "type": "video",
                "url": "https://example.com/candidate",
                "difficult": 0.3,
                "time_need": 10,
            }
        })
        graph = MagicMock()
        graph.rank_resource_similarity_pairs.return_value = [
            SimpleNamespace(id="candidate", reference_id="anchor-a", score=0.91),
            SimpleNamespace(id="candidate", reference_id="anchor-b", score=0.89),
        ]

        with patch("algorithm.graph_recommender.get_graph_recommender", return_value=graph):
            ranked, _, metadata = await agent._ranking_tool(
                {"schema": "similarity", "num": 5}, anchors, {"user_id": "learner-1"}, fallback_reason="sql_empty"
            )

        assert [item["id"] for item in ranked] == ["candidate", "candidate"]
        assert [item["similarity_reference_id"] for item in ranked] == ["anchor-a", "anchor-b"]
        assert ranked[0]["similarity_reference_title"] == "Anchor A"
        assert metadata["effective_schema"] == "similarity"
        assert metadata["ranking_backend"] == "text_embedding"
        graph.rank_resource_similarity_pairs.assert_called_once_with(["anchor-a", "anchor-b"], 5)

    @pytest.mark.asyncio
    async def test_missing_similarity_anchor_downgrades_to_personality_with_trace(self, _patch_llm):
        from app.services.agents.resource_recommender import ResourceRecommenderAgent

        agent = ResourceRecommenderAgent(llm=_patch_llm)
        full_catalog = [self._candidate("a"), self._candidate("b")]
        agent._sql_retrieval_tool = AsyncMock(return_value=[])
        agent._rank_similarity_pairs = AsyncMock(return_value=None)
        agent._load_all_resource_candidates = AsyncMock(return_value=full_catalog)
        agent._rank_with_graph = MagicMock(return_value=list(reversed(full_catalog)))

        result = await agent._execute_tools(
            {
                "tool_calls": [
                    {"tool_name": "SqlRetrievalTool", "input": {"sql": "SELECT id FROM learning_resources"}},
                    {"tool_name": "RankingTool", "input": {"schema": "similarity"}},
                ]
            },
            {"user_id": "learner-1"},
        )

        ranking = result["execution_context"]["ranking"]
        assert ranking["requested_schema"] == "similarity"
        assert ranking["effective_schema"] == "personality"
        assert ranking["fallback_reason"] == "missing_similarity_anchor"
        assert result["tool_trace"][1]["tool"] == "CandidateFallback"

    @pytest.mark.asyncio
    async def test_similarity_with_anchors_never_falls_back_to_personality(self, _patch_llm):
        from app.services.agents.resource_recommender import ResourceRecommenderAgent

        agent = ResourceRecommenderAgent(llm=_patch_llm)
        anchors = [self._candidate("anchor-a")]
        agent._rank_similarity_pairs = AsyncMock(return_value=None)
        agent._load_all_resource_candidates = AsyncMock()
        agent._rank_with_graph = MagicMock()

        ranked, returned_candidates, metadata = await agent._ranking_tool(
            {"schema": "similarity"},
            anchors,
            {"user_id": "learner-1"},
            fallback_reason="sql_empty",
        )

        assert ranked == []
        assert returned_candidates == anchors
        assert metadata["effective_schema"] == "similarity"
        assert metadata["similarity_status"] == "unavailable"
        agent._load_all_resource_candidates.assert_not_awaited()
        agent._rank_with_graph.assert_not_called()

    @pytest.mark.asyncio
    async def test_reflection_uses_effective_number_and_accepts_valid_fallbacks(self, _patch_llm):
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

        plan = {
            "need_tool": True,
            "tool_calls": [{"tool_name": "RankingTool", "input": {"schema": "personality", "num": 20}}],
        }
        tool_results = {
            "ranked_resources": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
            "tool_trace": [{"tool": "CandidateFallback", "status": "applied", "reason": "sql_not_called", "count": 3}],
            "execution_context": {
                "candidate_source": "full_catalog",
                "ranking": {
                    "effective_num": 15,
                    "candidate_count": 3,
                    "num_policy": "capped",
                    "effective_schema": "personality",
                    "fallback_reason": "missing_similarity_anchor",
                },
            },
        }
        reflection, _ = await agent._reflection(
            plan=plan,
            tool_results=tool_results,
            input_data={"current_message": "推荐很多资源", "recent_messages": []},
        )

        assert reflection["passed"] is True
        prompt = _patch_llm.chat_completion.await_args.kwargs["prompt"]
        assert "CandidateFallback" in prompt
        assert "effective_num" in prompt

        failed = agent._apply_reflection_checks(
            {"passed": True, "issues": [], "suggestion": "", "coverage_score": 1, "difficulty_match": 1, "diversity_score": 1},
            plan,
            {**tool_results, "ranked_resources": tool_results["ranked_resources"][:2]},
        )
        assert failed["passed"] is False
        assert "有效目标数量为 3，当前仅返回 2 条。" in failed["issues"]

    @pytest.mark.asyncio
    async def test_non_recommendation_returns_boundary_without_enrichment_or_tools(self, _patch_llm):
        from app.services.agents.resource_recommender import ResourceRecommenderAgent

        agent = ResourceRecommenderAgent(llm=_patch_llm)
        agent._generate_plan = AsyncMock(return_value=({"need_tool": False, "final_answer": ""}, {}))
        agent.enrich_input = AsyncMock()
        agent._execute_tools = AsyncMock()
        agent._summary = AsyncMock()
        agent._persist_recommendation = AsyncMock()
        agent._log_execution = AsyncMock()
        agent.post_process = AsyncMock()

        result = await agent.execute(
            {"user_id": "learner-1", "current_message": "牛顿第二定律是什么？", "recent_messages": []},
            context={},
        )

        assert result["output"]["recommendation_text"] == "该智能体仅处理学习资源推荐，请说明希望推荐的资源或学习目标。"
        assert result["output"]["resources"] == []
        agent.enrich_input.assert_not_awaited()
        agent._execute_tools.assert_not_awaited()
        agent._summary.assert_not_awaited()
        agent._persist_recommendation.assert_not_awaited()
        agent._log_execution.assert_not_awaited()

    def test_plan_keeps_only_sql_and_supported_ranking_schemas(self, _patch_llm):
        from app.services.agents.resource_recommender import ResourceRecommenderAgent

        plan = ResourceRecommenderAgent(llm=_patch_llm)._parse_plan(
            {
                "need_tool": True,
                "ranking_criteria": ["time_need", "personality", "difficulty", "similarity"],
                "tool_calls": [
                    {"tool_name": "UnsupportedTool", "input": {}},
                    {"tool_name": "SqlRetrievalTool", "input": {"sql": "SELECT id FROM learning_resources"}},
                    {"tool_name": "RankingTool", "input": {"schema": "time_need"}},
                    {"tool_name": "RankingTool", "input": {"schema": "personality"}},
                    {"tool_name": "RankingTool", "input": {"schema": "similarity"}},
                ],
            }
        )

        assert [call["tool_name"] for call in plan["tool_calls"]] == [
            "SqlRetrievalTool",
            "RankingTool",
            "RankingTool",
        ]
        assert [call["input"].get("schema") for call in plan["tool_calls"][1:]] == ["personality", "similarity"]
        assert plan["ranking_criteria"] == ["personality", "similarity"]

    def test_prompts_provide_schema_semantics_and_accept_multifield_or_in_reflection(self, _patch_llm):
        from app.services.agents.resource_recommender import ResourceRecommenderAgent

        agent = ResourceRecommenderAgent(llm=_patch_llm)
        plan_prompt = agent._render_stage_prompt(
            "plan",
            {
                "current_message": "有没有和牛顿运动定律类似的资源",
                "recent_messages": [],
                "target_knowledge": [],
                "difficulty": "",
                "learning_style": "",
                "diagnosis_result": {},
                "user_profile": {},
                "reflection_result": {},
            },
        )
        reflection_prompt = agent._render_stage_prompt(
            "reflection",
            {"current_message": "推荐资源", "plan": {}, "tool_results": {}},
        )

        for fragment in (
            "CREATE TABLE learning_resources",
            "CREATE TABLE knowledge_points",
            "CREATE TABLE resource_knowledge",
            "所属学科，如“物理”",
            "资源正文或简介",
            "lr.name",
            "lr.content",
            "rk.resource_id = lr.id",
            "kp.subject",
            "kp.grade/kp.grade_level",
            "kp.name",
            "kp.content",
            "LEFT JOIN",
            "完整的并列目标列表",
            "本轮 current_message 中明确表达",
        ):
            assert fragment in plan_prompt
        assert "分组 OR" in reflection_prompt
        assert "SELECT DISTINCT" in reflection_prompt
        assert "knowledge_points.subject" in reflection_prompt
        assert "num 缺失、不是整数、或不等于 2，必须输出 passed=false" in reflection_prompt
        assert "找两个类似资源" in plan_prompt

    @pytest.mark.parametrize(
        ("message", "sql", "schema", "num"),
        [
            ("推荐几个资源", "SELECT id FROM learning_resources", "personality", None),
            ("推荐几个物理资源", "SELECT DISTINCT lr.id FROM learning_resources AS lr JOIN resource_knowledge AS rk ON rk.resource_id = lr.id JOIN knowledge_points AS kp ON kp.id = rk.kp_id WHERE kp.subject = '物理'", "personality", None),
            ("从 A、B、C 中选一个推荐给我", "SELECT id FROM learning_resources WHERE name IN ('A', 'B', 'C')", "personality", 1),
            ("找几个与 A 和 B 相似的资源", "SELECT id FROM learning_resources WHERE name IN ('A', 'B')", "similarity", None),
        ],
    )
    def test_common_recommendation_plan_shapes(self, _patch_llm, message, sql, schema, num):
        from app.services.agents.resource_recommender import ResourceRecommenderAgent

        agent = ResourceRecommenderAgent(llm=_patch_llm)
        ranking_input = {"schema": schema}
        if num is not None:
            ranking_input["num"] = num
        plan = agent._parse_plan(
            {
                "need_tool": True,
                "tool_calls": [
                    {"tool_name": "SqlRetrievalTool", "input": {"sql": sql}},
                    {"tool_name": "RankingTool", "input": ranking_input},
                ],
            }
        )

        rendered_prompt = agent._render_stage_prompt(
            "plan",
            {
                "current_message": message,
                "recent_messages": [],
                "target_knowledge": [],
                "difficulty": "",
                "learning_style": "",
                "diagnosis_result": {},
                "user_profile": {},
            },
        )
        assert message in rendered_prompt
        assert plan["tool_calls"][0]["input"]["sql"] == sql
        assert plan["tool_calls"][1]["input"]["schema"] == schema
        assert plan["tool_calls"][1]["input"].get("num") == num

    @pytest.mark.asyncio
    async def test_persists_final_graph_or_similarity_fields(self, _patch_llm):
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
            "need_tool": True,
            "target_count": 1,
            "recall_strategy": "候选排序",
            "ranking_criteria": ["personality"],
            "tool_calls": [{"tool_name": "RankingTool", "input": {"schema": "personality", "num": 1}}],
        }
        reflection_response = {
            "passed": True,
            "issues": [],
            "suggestion": "",
            "coverage_score": 1,
            "difficulty_match": 1,
            "diversity_score": 1,
        }
        summary_response = {
            "recommendation_text": "推荐这一项资源。",
            "resources": [],
            "planning": {},
            "reflection": {},
            "tool_trace": [],
        }
        _patch_llm.chat_completion = AsyncMock(
            side_effect=[
                _mock_llm_response(plan_response),
                _mock_llm_response(reflection_response),
                _mock_llm_response(summary_response),
            ]
        )
        tool_results = {
            "candidates": [self._candidate("res-1")],
            "ranked_resources": [{**self._candidate("res-1"), "graph_score": 0.82, "rank": 1}],
            "tool_trace": [{"tool": "RankingTool", "status": "executed", "count": 1}],
            "execution_context": {"ranking": {"effective_num": 1, "candidate_count": 1}},
        }
        dummy_session = DummyAsyncSession()
        agent = ResourceRecommenderAgent(llm=_patch_llm)
        agent.enrich_input = AsyncMock(side_effect=lambda data, _context: data)
        agent._execute_tools = AsyncMock(return_value=tool_results)
        agent._log_execution = AsyncMock()
        agent.post_process = AsyncMock()

        with patch("app.database.AsyncSessionLocal", return_value=dummy_session):
            result = await agent.execute(
                {"user_id": "user-1", "current_message": "推荐一个资源", "recent_messages": []},
                context={"conversation_id": "conv-ctx", "user_id": "user-1", "log_execution": False},
            )

        record = dummy_session.added[0]
        assert dummy_session.committed is True
        assert record.rec_ranks["resources"][0]["graph_score"] == pytest.approx(0.82)
        assert result["output"]["recommendation_id"] == record.id


class TestStudyBuddy:
    @staticmethod
    def _candidate(user_id: str, *, nickname: str | None = None) -> dict[str, Any]:
        return {
            "user_id": user_id,
            "nickname": nickname or user_id,
            "current_level": "中级",
            "learning_style": "视觉",
            "grade_level": "高中",
            "weak_points": [],
            "knowledge_graph": {"牛顿运动定律": 0.9},
        }

    @pytest.mark.asyncio
    async def test_sql_candidates_are_graph_ranked_and_summary_keeps_execution_results(self, _patch_llm):
        from app.services.agents.study_buddy import StudyBuddyAgent

        plan = {
            "need_tool": True,
            "target_count": 1,
            "recall_strategy": "共同知识点召回",
            "ranking_criteria": ["personality"],
            "tool_calls": [
                {"tool_name": "SqlRetrievalTool", "input": {"sql": "SELECT id FROM users WHERE is_active = true"}},
                {"tool_name": "RankingTool", "input": {"schema": "personality", "num": 1}},
            ],
        }
        reflection = {"passed": True, "issues": [], "suggestion": "", "coverage_score": 1, "compatibility_score": 1, "diversity_score": 1}
        summary = {"recommendation_text": "推荐你先和小明一起复习。", "buddies": [], "planning": {}, "reflection": {}, "tool_trace": []}
        _patch_llm.chat_completion = AsyncMock(
            side_effect=[_mock_llm_response(plan), _mock_llm_response(reflection), _mock_llm_response(summary)]
        )

        agent = StudyBuddyAgent(llm=_patch_llm)
        candidate = self._candidate("u-456", nickname="小明")
        agent.enrich_input = AsyncMock(side_effect=lambda data, _context: data)
        agent._run_select_sql = AsyncMock(return_value=[{"id": "u-456"}])
        agent._fetch_buddy_details = AsyncMock(return_value=[candidate])
        agent._rank_with_graph = MagicMock(return_value=[{**candidate, "graph_score": 0.91}])
        agent._log_execution = AsyncMock()
        agent.post_process = AsyncMock()

        result = await agent.execute(
            {"user_id": "u-1", "current_message": "帮我找一个一起复习 Python 函数的学伴", "topic": "Python函数"},
            context={"persist_recommendation": False, "log_execution": False},
        )

        output = result["output"]
        assert _patch_llm.chat_completion.await_count == 3
        assert [item["tool"] for item in output["tool_trace"]] == ["SqlRetrievalTool", "RankingTool"]
        assert output["buddies"][0]["user_id"] == "u-456"
        assert output["buddies"][0]["graph_score"] == pytest.approx(0.91)
        assert output["plan_history"] == [agent._parse_plan(plan)]

    @pytest.mark.asyncio
    async def test_sql_retrieval_tool_returns_buddy_candidates(self, _patch_llm):
        from app.services.agents.study_buddy import StudyBuddyAgent

        agent = StudyBuddyAgent(llm=_patch_llm)
        candidate = self._candidate("u-2", nickname="同学乙")
        agent._run_select_sql = AsyncMock(return_value=[{"id": "u-2"}])
        agent._fetch_buddy_details = AsyncMock(return_value=[candidate])

        assert await agent._sql_retrieval_tool({"sql": "SELECT id FROM users WHERE is_active = true"}) == [candidate]

    @pytest.mark.asyncio
    async def test_missing_or_empty_sql_uses_full_catalog_before_ranking(self, _patch_llm):
        from app.services.agents.study_buddy import StudyBuddyAgent

        agent = StudyBuddyAgent(llm=_patch_llm)
        full_catalog = [self._candidate("u-2"), self._candidate("u-3")]
        agent._load_all_buddy_candidates = AsyncMock(return_value=full_catalog)
        agent._rank_with_graph = MagicMock(return_value=list(reversed(full_catalog)))
        missing_sql = await agent._execute_tools(
            {"tool_calls": [{"tool_name": "RankingTool", "input": {"schema": "personality"}}]},
            {"user_id": "u-1"},
        )
        assert [item["user_id"] for item in missing_sql["ranked_buddies"]] == ["u-3", "u-2"]
        assert missing_sql["tool_trace"][0]["reason"] == "sql_not_called"

        agent._sql_retrieval_tool = AsyncMock(return_value=[])
        empty_sql = await agent._execute_tools(
            {
                "tool_calls": [
                    {"tool_name": "SqlRetrievalTool", "input": {"sql": "SELECT id FROM users WHERE is_active = true"}},
                    {"tool_name": "RankingTool", "input": {"schema": "personality"}},
                ]
            },
            {"user_id": "u-1"},
        )
        assert empty_sql["tool_trace"][1]["reason"] == "sql_empty"
        assert empty_sql["execution_context"]["candidate_source"] == "full_catalog"

    @pytest.mark.asyncio
    async def test_ranking_number_policy_and_graph_fallback(self, _patch_llm):
        from app.services.agents.study_buddy import StudyBuddyAgent

        agent = StudyBuddyAgent(llm=_patch_llm)
        candidates = [self._candidate(f"u-{index}") for index in range(20)]
        agent._rank_with_graph = MagicMock(return_value=candidates)
        default_ranked, _, default_metadata = await agent._ranking_tool(
            {"schema": "personality"}, candidates, {"user_id": "u-current"}, fallback_reason="sql_empty"
        )
        capped_ranked, _, capped_metadata = await agent._ranking_tool(
            {"schema": "personality", "num": 20}, candidates, {"user_id": "u-current"}, fallback_reason="sql_empty"
        )
        assert len(default_ranked) == 5
        assert default_metadata["num_policy"] == "default"
        assert len(capped_ranked) == 15
        assert capped_metadata["num_policy"] == "capped"

        agent._rank_with_graph = MagicMock(return_value=None)
        fallback_ranked, _, fallback_metadata = await agent._ranking_tool(
            {"schema": "personality", "num": 2}, candidates[:2], {"user_id": "u-current"}, fallback_reason="sql_empty"
        )
        assert [item["user_id"] for item in fallback_ranked] == ["u-0", "u-1"]
        assert fallback_metadata["ranking_backend"] == "deterministic_fallback"

    @pytest.mark.asyncio
    async def test_similarity_ranking_uses_graph_aggregated_embeddings(self, _patch_llm):
        from app.services.agents.study_buddy import StudyBuddyAgent

        agent = StudyBuddyAgent(llm=_patch_llm)
        candidates = [self._candidate("u-2"), self._candidate("u-3")]
        agent._similarity_with_graph = MagicMock(
            return_value=[{**candidates[1], "similarity_score": 0.75}, {**candidates[0], "similarity_score": 0.25}]
        )
        agent._rank_with_graph = MagicMock()
        ranked, _, metadata = await agent._ranking_tool(
            {"schema": "similarity", "num": 1}, candidates, {"user_id": "u-1"}, fallback_reason="sql_empty"
        )
        assert [item["user_id"] for item in ranked] == ["u-3"]
        assert ranked[0]["similarity_score"] == pytest.approx(0.75)
        assert metadata["ranking_backend"] == "graph_similarity"
        agent._similarity_with_graph.assert_called_once()
        agent._rank_with_graph.assert_not_called()

    def test_plan_keeps_only_sql_and_supported_ranking_schemas(self, _patch_llm):
        from app.services.agents.study_buddy import StudyBuddyAgent

        plan = StudyBuddyAgent(llm=_patch_llm)._parse_plan(
            {
                "need_tool": True,
                "ranking_criteria": ["unsupported_schema", "personality", "similarity"],
                "tool_calls": [
                    {"tool_name": "UnsupportedTool", "input": {}},
                    {"tool_name": "SqlRetrievalTool", "input": {"sql": "SELECT id FROM users"}},
                    {"tool_name": "RankingTool", "input": {"schema": "unsupported_schema"}},
                    {"tool_name": "RankingTool", "input": {"schema": "personality"}},
                    {"tool_name": "RankingTool", "input": {"schema": "similarity"}},
                ],
            }
        )
        assert [call["tool_name"] for call in plan["tool_calls"]] == ["SqlRetrievalTool", "RankingTool", "RankingTool"]
        assert [call["input"]["schema"] for call in plan["tool_calls"][1:]] == ["personality", "similarity"]
        assert plan["ranking_criteria"] == ["personality", "similarity"]

    @pytest.mark.asyncio
    async def test_reflection_uses_effective_number_and_accepts_full_catalog_fallback(self, _patch_llm):
        from app.services.agents.study_buddy import StudyBuddyAgent

        _patch_llm.chat_completion = AsyncMock(
            return_value=_mock_llm_response({"passed": True, "issues": [], "suggestion": "", "coverage_score": 1, "compatibility_score": 1, "diversity_score": 1})
        )
        agent = StudyBuddyAgent(llm=_patch_llm)
        plan = {"need_tool": True, "tool_calls": [{"tool_name": "RankingTool", "input": {"schema": "personality", "num": 20}}]}
        tool_results = {
            "ranked_buddies": [self._candidate("u-2"), self._candidate("u-3")],
            "tool_trace": [{"tool": "CandidateFallback", "status": "applied", "reason": "sql_not_called", "count": 2}],
            "execution_context": {"ranking": {"effective_num": 15, "eligible_candidate_count": 2, "candidate_count": 2, "num_policy": "capped"}},
        }
        reflection, _ = await agent._reflection(plan, tool_results, {"current_message": "推荐很多学伴", "recent_messages": []})
        assert reflection["passed"] is True
        assert "CandidateFallback" in _patch_llm.chat_completion.await_args.kwargs["prompt"]

        failed = agent._apply_reflection_checks(
            {"passed": True, "issues": [], "suggestion": "", "coverage_score": 1, "compatibility_score": 1, "diversity_score": 1},
            plan,
            {**tool_results, "ranked_buddies": tool_results["ranked_buddies"][:1]},
        )
        assert failed["passed"] is False
        assert "有效目标数量为 2，当前仅返回 1 位学伴。" in failed["issues"]

    @pytest.mark.asyncio
    async def test_persists_graph_scores_and_execution_context(self, _patch_llm):
        from app.services.agents.study_buddy import StudyBuddyAgent

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

        buddy = {**self._candidate("u-2"), "graph_score": 0.82, "similarity_score": 0.64, "rank": 1}
        dummy_session = DummyAsyncSession()
        agent = StudyBuddyAgent(llm=_patch_llm)

        with patch("app.database.AsyncSessionLocal", return_value=dummy_session):
            recommendation_id = await agent._persist_recommendation(
                {"buddies": [buddy], "planning": {"recall_strategy": "候选排序"}, "reflection": {}, "tool_trace": []},
                {"user_id": "u-1"},
                {"conversation_id": "conv-1"},
                {"candidates": [self._candidate("u-2")], "execution_context": {"ranking": {"effective_num": 1}}},
                [{"need_tool": True}],
                [{"passed": True}],
            )

        record = dummy_session.added[0]
        assert dummy_session.committed is True
        assert recommendation_id == record.id
        assert record.rec_ranks["buddies"][0]["graph_score"] == pytest.approx(0.82)
        assert record.rec_ranks["buddies"][0]["similarity_score"] == pytest.approx(0.64)
        assert record.train_labels["execution_context"]["ranking"]["effective_num"] == 1

    @pytest.mark.asyncio
    async def test_non_recommendation_returns_boundary_without_enrichment_or_tools(self, _patch_llm):
        from app.services.agents.study_buddy import StudyBuddyAgent

        agent = StudyBuddyAgent(llm=_patch_llm)
        agent._generate_plan = AsyncMock(return_value=({"need_tool": False, "final_answer": ""}, {}))
        agent.enrich_input = AsyncMock()
        agent._execute_tools = AsyncMock()
        agent._summary = AsyncMock()
        agent._persist_recommendation = AsyncMock()
        agent._log_execution = AsyncMock()
        agent.post_process = AsyncMock()
        result = await agent.execute(
            {"user_id": "u-1", "current_message": "牛顿第二定律是什么？", "recent_messages": []}, context={}
        )
        assert result["output"]["recommendation_text"] == "该智能体仅处理学习伙伴推荐，请说明希望寻找的学习伙伴或共同学习目标。"
        assert result["output"]["buddies"] == []
        agent.enrich_input.assert_not_awaited()
        agent._execute_tools.assert_not_awaited()
        agent._summary.assert_not_awaited()
        agent._persist_recommendation.assert_not_awaited()
        agent._log_execution.assert_not_awaited()


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


class TestContentCorrector:
    def test_prompt_treats_safety_as_constraint_not_unrelated_topic(self, _patch_llm):
        from app.services.agents.content_corrector import ContentCorrectorAgent

        agent = ContentCorrectorAgent(llm=_patch_llm)
        prompt = agent._render_prompt(
            {
                "original_response": "可以先准备一张长方形纸。",
                "student_question": "怎么制作小纸船？",
                "subject": "劳动与技术",
                "grade_level": "小学",
                "conversation_stage": "teaching",
                "safety_constraints": {"branch": "PASS"},
            }
        )

        assert "当前轮明确提供的有效信息支持" in prompt
        assert "不会自动改变当前问题的主题" in prompt

    @pytest.mark.asyncio
    async def test_audit_without_rewrite(self, _patch_llm):
        from app.services.agents.content_corrector import ContentCorrectorAgent

        original = "电流可能影响神经和肌肉活动，影响程度与电流路径和持续时间有关。"
        expected = {
            "action": "PASS",
            "issues": [],
            "patched_response": "",
            "checks": {
                "scientific_reliability": True,
                "educational_completeness": True,
                "structural_clarity": True,
                "content_safety": True,
            },
        }
        _patch_llm.chat_completion = AsyncMock(return_value=_mock_llm_response(expected))
        _patch_llm.validate_json_response = AsyncMock(return_value=expected)

        agent = ContentCorrectorAgent(llm=_patch_llm)
        result = await agent.execute(
            {"original_response": original, "student_question": "电流有什么影响？"},
            context={"conversation_id": "conv-corrector"},
        )

        assert result["agent"] == "content_corrector"
        assert result["output"]["action"] == "PASS"
        assert result["output"]["patched_response"] == ""


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
        assert "content_corrector" in names
        assert len(agents) == 10  # 9 个教育智能体 + safety_monitor

    def test_get_agent(self):
        from app.services.agents import get_agent

        agent = get_agent("safety_monitor")
        assert agent.name == "safety_monitor"

    def test_get_unknown_raises(self):
        from app.services.agents import get_agent

        with pytest.raises(KeyError):
            get_agent("nonexistent_agent")
