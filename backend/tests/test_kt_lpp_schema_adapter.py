from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from jsonschema import validate

from app.config import settings
from app.services import kt_integration
from app.services.agents.cognitive_diagnosis import CognitiveDiagnosisAgent
from app.services.agents.knowledge_responder import KnowledgeResponderAgent
from app.services.agents.learning_path import LearningPathAgent
from app.services.lpp_integration import LppRuntimeOutput


def test_student_id_resolution_priority():
    assert settings.kt.demo_student_id == "43"
    assert (
        kt_integration.resolve_kt_student_id(
            {"student_id": "9", "current_message": "分析学生21"},
            {"kt_student_id": "12"},
        )
        == "9"
    )
    assert (
        kt_integration.resolve_kt_student_id(
            {"current_message": "请分析学生21的学习情况"},
            {},
        )
        == "21"
    )
    assert (
        kt_integration.resolve_kt_student_id(
            {
                "user_profile": {
                    "preferences": {"kt_student_id": "17"},
                }
            },
            {},
        )
        == "17"
    )
    assert (
        kt_integration.resolve_kt_student_id(
            {"student_id": "99f4fb38-f21d-47af-aa99-dccb046a1d2f"},
            {"student_id": "99f4fb38-f21d-47af-aa99-dccb046a1d2f"},
        )
        == "43"
    )
    assert kt_integration.resolve_kt_student_id({}, {}) == "43"


def test_kt_normalization_supplies_original_schema_fields():
    result = kt_integration._normalize_kt_output(
        {
            "predictions": [
                {
                    "target": {
                        "skill_id": 17,
                        "extras": {
                            "knowledge_point_name": "物质分类",
                            "knowledge_point_type": "概念",
                        },
                    },
                    "probability_correct": 0.25,
                }
            ],
            "metrics": {"auc": 0.8},
            "model_info": {"name": "KT"},
        }
    )

    state = result["knowledge_states"][0]
    assert state["skill_id"] == "17"
    assert state["skill_name"] == "物质分类"
    assert state["type"] == "概念"
    assert state["mastery_percent"] == "25.0%"
    assert state["mastery_label"] == "较低"
    assert result["mastery_rates"] == {"17": 0.25}
    assert result["diagnosis_source"] == "kt"


def test_kt_normalization_keeps_only_skill_selected_top_18():
    predictions = [
        {
            "target": {
                "skill_id": skill_id,
                "extras": {"knowledge_point_name": f"知识点{skill_id}"},
            },
            "probability_correct": 0.2 if skill_id % 2 else 0.8,
        }
        for skill_id in range(1, 335)
    ]
    selected_ids = list(range(118, 100, -1))

    result = kt_integration._normalize_kt_output(
        {
            "predictions": predictions,
            "llm_analysis": {
                "selected_knowledge_points": [
                    {"source_skill_id": skill_id}
                    for skill_id in selected_ids
                ]
            },
        }
    )

    assert [state["skill_id"] for state in result["knowledge_states"]] == [
        str(skill_id) for skill_id in selected_ids
    ]
    assert set(result["mastery_rates"]) == {
        str(skill_id) for skill_id in selected_ids
    }
    assert {state["skill_id"] for state in result["weak_points"]} <= {
        str(skill_id) for skill_id in selected_ids
    }


def test_mastery_probability_prefers_numeric_rate_and_accepts_decimal_percent():
    assert CognitiveDiagnosisAgent._mastery_probability(
        {"mastery_rate": 0.25, "mastery_percent": "99.0%"}
    ) == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_diagnosis_profile_replaces_prior_unselected_knowledge_states(
    monkeypatch,
):
    profile = SimpleNamespace(
        user_id="user-1",
        knowledge_graph={"old-unselected": 0.1, "17": 0.2, "_graph": {"old": True}},
        weak_points=[{"skill_id": "old-unselected"}],
        last_diagnosis=None,
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def execute(self, statement):
            return SimpleNamespace(scalar_one_or_none=lambda: profile)

        def add(self, item):
            assert item is profile

        async def commit(self):
            return None

    monkeypatch.setattr(
        "app.services.agents.cognitive_diagnosis.AsyncSessionLocal",
        lambda: FakeSession(),
    )

    agent = CognitiveDiagnosisAgent(llm=MagicMock())
    await agent.post_process(
        {
            "knowledge_states": [{"skill_id": "17", "mastery_rate": 0.25}],
            "weak_points": [{"skill_id": "17"}],
            "knowledge_graph": {"nodes": [{"id": "17"}]},
        },
        {"user_id": profile.user_id},
    )

    assert profile.knowledge_graph == {
        "17": 0.25,
        "_graph": {"nodes": [{"id": "17"}]},
    }
    assert profile.weak_points == [{"skill_id": "17"}]


def _diagnosis_states() -> list[dict]:
    states = [
        {
            "skill_id": f"weak-{index}",
            "skill_name": f"薄弱知识点{index}",
            "type": "概念",
            "mastery_rate": index / 100,
            "mastery_percent": f"{index}%",
            "mastery_label": "较低",
            "status": "weak",
            "evidence": "KT 模型预测",
        }
        for index in range(25)
    ]
    states.extend(
        {
            "skill_id": f"developing-{index}",
            "skill_name": f"发展中知识点{index}",
            "type": "规律",
            "mastery_rate": 0.4 + index / 100,
            "mastery_percent": f"{40 + index}%",
            "mastery_label": "中等",
            "status": "developing",
            "evidence": "KT 模型预测",
        }
        for index in range(10)
    )
    states.extend(
        {
            "skill_id": f"mastered-{index}",
            "skill_name": f"已掌握知识点{index}",
            "type": "方法",
            "mastery_rate": 0.8 + index / 100,
            "mastery_percent": f"{80 + index}%",
            "mastery_label": "良好",
            "status": "mastered",
            "evidence": "KT 模型预测",
        }
        for index in range(5)
    )
    return states


def test_kt_prompt_context_is_bounded_and_nonduplicative():
    context = kt_integration.build_kt_prompt_context(
        {
            "knowledge_states": _diagnosis_states(),
            "mastery_rates": {"unused": 0.1},
            "weak_points": [{"skill_id": "unused"}],
        }
    )

    selected = context["priority_states"]
    assert len(selected) == 18
    assert sum(item["status"] == "weak" for item in selected) == 10
    assert sum(item["status"] == "developing" for item in selected) == 5
    assert sum(item["status"] == "mastered" for item in selected) == 3
    assert len({item["skill_id"] for item in selected}) == len(selected)
    assert context["total_count"] == 40
    assert context["weak_count"] == 25
    assert "knowledge_states" not in context
    assert "mastery_rates" not in context
    assert "weak_points" not in context


def test_feature_agent_token_limits_bound_followup_generation():
    assert CognitiveDiagnosisAgent(llm=MagicMock()).llm_config["max_tokens"] == 1024
    assert LearningPathAgent(llm=MagicMock()).llm_config["max_tokens"] == 1024


@pytest.mark.parametrize(
    "agent_class",
    [CognitiveDiagnosisAgent, LearningPathAgent],
)
def test_kt_lpp_explanation_agents_inherit_global_llm_endpoint_and_model(
    monkeypatch,
    agent_class,
):
    monkeypatch.setattr(settings.llm, "base_url", "https://llm.example.test/v1")
    monkeypatch.setattr(settings.llm, "model_name", "global-explanation-model")

    agent = agent_class()

    assert str(agent.llm._client.base_url).rstrip("/") == "https://llm.example.test/v1"
    assert agent.llm._default_model == "global-explanation-model"


def test_diagnosis_prompt_context_is_bounded_for_learning_path():
    from app.services.lpp_integration import build_diagnosis_prompt_context

    context = build_diagnosis_prompt_context(
        {
            "diagnosis_summary": "需要优先巩固基础概念。",
            "recommended_actions": ["先完成基础练习"],
            "knowledge_states": _diagnosis_states(),
            "mastery_rates": {"unused": 0.1},
            "weak_points": [{"skill_id": "unused"}],
            "knowledge_graph": {"nodes": ["unused"]},
        }
    )

    assert context["diagnosis_summary"] == "需要优先巩固基础概念。"
    assert context["recommended_actions"] == ["先完成基础练习"]
    assert len(context["priority_states"]) == 10
    assert [item["skill_id"] for item in context["priority_states"]] == [
        f"weak-{index}" for index in range(10)
    ]
    assert context["total_count"] == 40
    assert "knowledge_states" not in context
    assert "mastery_rates" not in context
    assert "weak_points" not in context
    assert "knowledge_graph" not in context
    assert CognitiveDiagnosisAgent._mastery_probability(
        {"mastery_percent": "25.0%"}
    ) == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_knowledge_responder_prompt_uses_bounded_kt_and_lpp_context():
    diagnosis = {
        "topic_analysis": "当前主题为科学学情诊断。",
        "diagnosis_summary": "需要优先巩固基础概念。",
        "cognitive_attribution": {"root_causes": ["前置知识不牢固"]},
        "recommended_actions": ["先完成基础练习"],
        "diagnosis_source": "kt",
        "kt_student_id": "43",
        "knowledge_states": _diagnosis_states(),
        "mastery_rates": {"full-mastery-rates-secret": 0.1},
        "weak_points": [{"evidence": "full-weak-points-secret"}],
        "knowledge_graph": {"secret": "full-knowledge-graph-secret"},
        "kt_metrics": {"secret": "full-metrics-secret"},
        "kt_model_info": {"secret": "full-model-info-secret"},
    }
    learning_plan = {
        "planning_rationale": "按照先基础后迁移的顺序安排练习。",
        "total_estimated_time": "约50分钟",
        "adaptive_rules": "答错时回到对应知识点进行补救。",
        "milestones": [f"完成 P{index}" for index in range(1, 6)],
        "path_adjustment_triggers": {
            "accelerate": "五题全部答对",
            "remediate": "基础题答错",
            "redirect": "安全判断题答错",
        },
        "recommended_knowledge_points": _lpp_runtime_result()["recommendation"]["knowledge_points"],
        "learning_path": [{"secret": "full-learning-path-secret"}],
        "stages": [{"secret": "duplicate-stages-secret"}],
        "target": {"secret": "full-target-secret"},
    }
    agent = KnowledgeResponderAgent(llm=MagicMock())

    enriched = await agent.enrich_input(
        {
            "current_message": "请汇总诊断和学习路径",
            "recent_messages": [],
            "stage": "diagnosis_and_plan",
            "diagnosis_result": diagnosis,
            "learning_plan": learning_plan,
            "cognitive_diagnosis": diagnosis,
            "learning_path": learning_plan,
            "mastery_rates": {"raw-context-secret": 0.1},
            "knowledge_graph": {"secret": "raw-graph-secret"},
            "user_profile": {
                "current_level": "初级",
                "learning_style": "视觉型",
                "grade_level": "五年级",
                "weak_points": [{"secret": "profile-weak-points-secret"}],
                "knowledge_graph": {"secret": "profile-graph-secret"},
                "preferences": {"secret": "profile-preferences-secret"},
            },
        },
        {},
    )
    rendered = agent._render_prompt(enriched)

    assert enriched["diagnosis_result"]["total_count"] == 40
    assert enriched["diagnosis_result"]["weak_count"] == 25
    assert [
        state["skill_id"]
        for state in enriched["diagnosis_result"]["priority_states"]
    ] == [f"weak-{index}" for index in range(10)]
    assert enriched["diagnosis_result"]["diagnosis_summary"] == "需要优先巩固基础概念。"
    assert enriched["diagnosis_result"]["cognitive_attribution"] == {
        "root_causes": ["前置知识不牢固"]
    }
    assert [
        point["order"]
        for point in enriched["learning_plan"]["recommended_knowledge_points"]
    ] == [1, 2, 3, 4, 5]
    assert enriched["learning_plan"]["planning_rationale"] == (
        "按照先基础后迁移的顺序安排练习。"
    )
    assert enriched["user_profile"] == {
        "current_level": "初级",
        "learning_style": "视觉型",
        "grade_level": "五年级",
        "weak_points": [f"薄弱知识点{index}" for index in range(10)],
    }
    assert "cognitive_diagnosis" not in enriched
    assert "learning_path" not in enriched
    assert "mastery_rates" not in enriched
    assert "knowledge_graph" not in enriched
    for forbidden in (
        "full-mastery-rates-secret",
        "full-weak-points-secret",
        "full-knowledge-graph-secret",
        "full-metrics-secret",
        "full-model-info-secret",
        "full-learning-path-secret",
        "duplicate-stages-secret",
        "full-target-secret",
        "raw-context-secret",
        "raw-graph-secret",
        "profile-weak-points-secret",
        "profile-graph-secret",
        "profile-preferences-secret",
    ):
        assert forbidden not in rendered


def _lpp_runtime_result() -> dict:
    questions = []
    for order in range(1, 6):
        questions.append(
            {
                "question_id": 100 + order,
                "question_text": f"第{order}道题",
                "question_type": "判断题",
                "options": [],
                "knowledge_points": [
                    {
                        "knowledge_point_id": 10 + order,
                        "knowledge_point_name": f"知识点{order}",
                    }
                ],
                "order": order,
            }
        )
    return {
        "status": "ok",
        "message": "recommendations_ready",
        "student_id": "43",
        "target": {"question_id": 99, "question_text": "目标题"},
        "recommendation": {
            "count": 5,
            "questions": questions,
            "knowledge_points": [
                {
                    "order": order,
                    "knowledge_point_id": 10 + order,
                    "knowledge_point_name": f"知识点{order}",
                }
                for order in range(1, 6)
            ],
        },
        "plan_items": [],
        "diagnostics": {"initial_target_source": "default"},
    }


@pytest.mark.asyncio
async def test_learning_path_prompt_boundary_removes_full_runtime_and_profile_data():
    runtime = _lpp_runtime_result()
    runtime["diagnostics"] = {"secret": "runtime-diagnostics-secret"}
    runtime["plan_items"] = [
        {
            "priority": "P1",
            "question_id": 101,
            "purpose_and_effect": "先建立呼吸器官的基础认识。",
            "knowledge_sequences": ["runtime-sequence-secret"],
            "related_questions": ["runtime-related-secret"],
        }
    ]
    diagnosis = {
        "diagnosis_summary": "优先修复基础知识。",
        "recommended_actions": ["先做基础题"],
        "diagnosis_source": "kt",
        "knowledge_states": _diagnosis_states(),
        "mastery_rates": {"profile-full-rates-secret": 0.1},
        "weak_points": [{"evidence": "diagnosis-full-weak-secret"}],
        "knowledge_graph": {
            "nodes": [
                {"id": "11", "name": "知识点1"},
                {"id": "999", "name": "graph-unrelated-secret"},
            ],
            "edges": [
                {"source": "11", "target": "999", "relation": "related"},
            ],
        },
    }
    profile = {
        "current_level": "初级",
        "learning_style": "视觉型",
        "grade_level": "五年级",
        "weak_points": [{"evidence": "profile-weak-secret"}],
        "knowledge_graph": {"secret": "profile-graph-secret"},
        "preferences": {"secret": "profile-preferences-secret"},
    }
    agent = LearningPathAgent(llm=MagicMock())

    enriched = await agent.enrich_input(
        {
            "current_message": "请规划学习路径",
            "recent_messages": [],
            "diagnosis_result": diagnosis,
            "knowledge_graph": diagnosis["knowledge_graph"],
            "user_profile": profile,
            "lpp_runtime": runtime,
        },
        {},
    )
    rendered = agent._render_prompt(enriched)

    assert enriched["user_profile"] == {
        "current_level": "初级",
        "learning_style": "视觉型",
        "grade_level": "五年级",
    }
    assert len(enriched["diagnosis_result"]["priority_states"]) == 10
    assert enriched["knowledge_graph"] == {
        "nodes": [{"id": "11", "name": "知识点1"}],
        "edges": [],
    }
    assert [
        point["order"]
        for point in enriched["lpp_runtime"]["recommendation"]["knowledge_points"]
    ] == [1, 2, 3, 4, 5]
    for forbidden in (
        "runtime-diagnostics-secret",
        "runtime-sequence-secret",
        "runtime-related-secret",
        "diagnosis-full-weak-secret",
        "profile-weak-secret",
        "profile-graph-secret",
        "profile-preferences-secret",
        "profile-full-rates-secret",
        "graph-unrelated-secret",
    ):
        assert forbidden not in rendered


def test_lpp_contract_requires_exactly_five_ordered_knowledge_points():
    from app.services.lpp_integration import validate_lpp_result

    validate_lpp_result(_lpp_runtime_result())

    broken = _lpp_runtime_result()
    broken["recommendation"]["knowledge_points"].pop()
    with pytest.raises(ValueError, match="exactly 5"):
        validate_lpp_result(broken)

    reordered = _lpp_runtime_result()
    reordered["recommendation"]["knowledge_points"][4]["order"] = 4
    with pytest.raises(ValueError, match="consecutive"):
        validate_lpp_result(reordered)


def test_learning_path_llm_contract_requests_explanation_fields_only():
    from jsonschema import validate

    agent = LearningPathAgent(llm=MagicMock())
    validate(
        {
            "planning_rationale": "先修复薄弱知识点，再按固定顺序完成五步学习。",
            "adaptive_rules": "每一步完成后根据掌握情况决定继续或复习。",
        },
        agent.output_schema,
    )

    rendered = agent._render_prompt(
        {
            "current_message": "请规划学习路径",
            "recent_messages": [],
            "diagnosis_result": {},
            "knowledge_graph": {},
            "goal": "掌握薄弱知识点",
            "user_profile": {},
            "lpp_runtime": {"recommendation": {"knowledge_points": []}},
        }
    )
    assert '"learning_path"' not in rendered
    assert '"planning_rationale"' in rendered
    assert '"adaptive_rules"' in rendered


@pytest.mark.asyncio
async def test_cognitive_agent_uses_default_student_and_runtime_facts(monkeypatch):
    monkeypatch.setattr(
        "app.services.agents.cognitive_diagnosis.retrieve_topic_knowledge",
        AsyncMock(return_value={
            "status": "ok", "method": "llm_closed_catalog", "topic_context": {},
            "queries": {"core": ["物质分类"], "prerequisite": [], "safety_ethics": [], "application": []},
            "matches": [{"skill_id": 17, "skill_name": "物质分类", "role": "core", "reason": "对应分类学习主题"}],
        }),
    )
    runtime = {
        "knowledge_states": [
            {
                "skill_id": "17",
                "skill_name": "物质分类",
                "type": "概念",
                "mastery_percent": "25.0%",
                "mastery_rate": 0.25,
                "mastery_label": "较低",
                "status": "weak",
            }
        ],
        "mastery_rates": {"17": 0.25},
        "weak_points": [{"skill_id": "17", "skill_name": "物质分类"}],
        "metrics": {"auc": 0.8},
        "model_info": {"name": "KT"},
    }
    llm = MagicMock()
    llm.chat_completion = AsyncMock(
        return_value={
            "content": {
                "topic_analysis": "物质分类主题",
                "knowledge_states": [{"skill_id": "fake"}],
                "cognitive_attribution": {"root_causes": []},
                "weak_points": [],
                "diagnosis_summary": "需要巩固分类依据。",
                "recommended_actions": ["复习分类标准"],
                "knowledge_graph": {"nodes": [], "edges": []},
            },
            "usage": {},
        }
    )
    llm.validate_json_response = AsyncMock(side_effect=lambda content, schema: content)
    agent = CognitiveDiagnosisAgent(llm=llm)
    agent._run_kt_diagnosis = AsyncMock(return_value=runtime)
    agent._log_execution = AsyncMock()
    agent.post_process = AsyncMock()
    monkeypatch.setattr(settings.kt, "mode", "integrated")

    result = await agent.execute(
        {"current_message": "分析一下我的学情", "recent_messages": []},
        {},
    )

    output = result["output"]
    agent._run_kt_diagnosis.assert_awaited_once()
    assert agent._run_kt_diagnosis.await_args.args[0] == "43"
    assert output["knowledge_states"][0]["skill_id"] == "17"
    assert output["mastery_rates"] == {"17": 0.25}
    assert [(point["skill_id"], point["skill_name"]) for point in output["weak_points"]] == [(point["skill_id"], point["skill_name"]) for point in runtime["weak_points"]]
    assert output["weak_points"][0]["mastery_rate"] == 0.25
    assert output["diagnosis_source"] == "kt"
    assert output["diagnosis_summary"] == "需要巩固分类依据。"
    validate(instance=output, schema=agent.output_schema)
    agent.post_process.assert_awaited_once()
    persisted_output = agent.post_process.await_args.args[0]
    assert persisted_output["knowledge_states"][0]["skill_id"] == "17"


@pytest.mark.asyncio
async def test_learning_path_exposes_runtime_knowledge_points_and_aliases(monkeypatch):
    runtime_data = _lpp_runtime_result()
    runtime_data["target"]["knowledge_points"] = [{"knowledge_point_id": 11, "knowledge_point_name": "知识点1"}]
    monkeypatch.setattr(
        "app.services.agents.learning_path.retrieve_topic_knowledge",
        AsyncMock(return_value={
            "status": "ok", "method": "llm_closed_catalog", "topic_context": {},
            "queries": {"core": ["本轮学习主题"], "prerequisite": [], "safety_ethics": [], "application": []},
            "matches": [{"skill_id": 10 + i, "skill_name": f"知识点{i}", "role": "core", "reason": "对应本轮学习主题"} for i in range(1, 6)],
        }),
    )
    run_lpp = AsyncMock(
        return_value=LppRuntimeOutput(data=runtime_data, raw_json="{}")
    )
    monkeypatch.setattr(
        "app.services.agents.learning_path.run_lpp_for_student",
        run_lpp,
        raising=False,
    )
    llm = MagicMock()
    llm.chat_completion = AsyncMock(
        return_value={
            "content": {
                "planning_rationale": "根据知识点优先级安排五步学习。",
                "learning_path": [{"stage_id": "fake"}],
                "total_estimated_time": "错误时间",
                "adaptive_rules": "答错时先复习对应知识点。",
                "recommended_knowledge_points": [{"order": 99}],
            },
            "usage": {},
        }
    )
    llm.validate_json_response = AsyncMock(side_effect=lambda content, schema: content)
    agent = LearningPathAgent(llm=llm)
    agent._log_execution = AsyncMock()

    result = await agent.execute(
        {"current_message": "请规划一条学习路径", "recent_messages": []},
        {},
    )

    output = result["output"]
    run_lpp.assert_awaited_once()
    assert run_lpp.await_args.args[0] == "43"
    assert output["learning_path"] == output["stages"]
    assert len(output["learning_path"]) == 5
    assert [stage["stage_id"] for stage in output["learning_path"]] == [
        "P1",
        "P2",
        "P3",
        "P4",
        "P5",
    ]
    assert output["total_estimated_time"] == output["estimated_completion"]
    assert [point["order"] for point in output["recommended_knowledge_points"]] == [1, 2, 3, 4, 5]
    assert "recommended_questions" not in output
    assert output["lpp_source"] == "lpp_runtime"
    assert all(stage["name"] in output["planning_rationale"] for stage in output["learning_path"])
    assert "对应本轮学习主题" in output["planning_rationale"]


@pytest.mark.asyncio
async def test_kt_command_timeout_kills_process_group(monkeypatch):
    class HangingProcess:
        pid = 43210
        returncode = None

        async def communicate(self):
            await __import__("asyncio").Future()

        async def wait(self):
            return -9

    create_process = AsyncMock(return_value=HangingProcess())
    killpg = MagicMock()
    monkeypatch.setattr(kt_integration.asyncio, "create_subprocess_exec", create_process)
    monkeypatch.setattr(kt_integration.os, "killpg", killpg)
    monkeypatch.setattr(settings.kt, "timeout_seconds", 0.01)

    with pytest.raises(RuntimeError, match="timed out"):
        await kt_integration._run_kt_command(["--student-id", "43"])

    killpg.assert_called_once_with(43210, kt_integration.signal.SIGKILL)
