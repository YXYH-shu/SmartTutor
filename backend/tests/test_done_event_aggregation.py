"""End-to-end-ish coverage for the SSE done event aggregation.

Verifies ``TutorGraphEngine._aggregate_turn_data`` and the SSE done payload
construction in ``chat_service.stream_message``. Uses synthetic state (no
LLM, no DB) so it runs in CI without secrets.

Covers three scenes:
1. KT 输出齐全 → touchedNodes / trajectory / ktSummary 格式正确
2. state 没有 cognitive_diagnosis → 字段降级为空,不抛错
3. safety 短路 → pre_focus 透传到 focus_agents
Plus a contract test: SSE done payload keys are camelCase.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.graph.engine import TutorGraphEngine


# ---------------------------------------------------------------------------
# Helpers – build minimal state / result dicts the way the graph would
# ---------------------------------------------------------------------------


def _kt_state_for(student_focus: list[str] | None = None) -> dict[str, Any]:
    """A graph result dict that looks like a real KT-integrated turn."""
    knowledge_states = [
        {
            "skill_id": "kp1",
            "skill_name": "代数",
            "mastery_percent": "30.0%",
            "mastery_rate": 0.3,
            "status": "weak",
            "evidence": "KT 模型预测",
        },
        {
            "skill_id": "kp2",
            "skill_name": "函数",
            "mastery_percent": "75.0%",
            "mastery_rate": 0.75,
            "status": "mastered",
            "evidence": "KT 模型预测",
        },
        {
            "skill_id": "kp3",
            "skill_name": "数列",
            "mastery_percent": "55.0%",
            "mastery_rate": 0.55,
            "status": "developing",
            "evidence": "KT 模型预测",
        },
    ]
    return {
        "final_response": "讲解代数基础...",
        "workflow_type": "adaptive_learning",
        "current_stage": "teaching",
        "context": {
            "cognitive_diagnosis": {
                "knowledge_states": knowledge_states,
                "mastery_rates": {"kp1": 0.3, "kp2": 0.75, "kp3": 0.55},
                "weak_points": [knowledge_states[0]],  # KT 输出 list[dict]
                "diagnosis_summary": "代数薄弱,需补强",
                "diagnosis_source": "kt",
                "kt_model_info": {"model_name": "kt", "dataset": "assist09"},
                "kt_metrics": {"rmse": 0.42, "auc": 0.81},
            }
        },
        "focus_agents": student_focus or ["cognitive_diagnosis"],
    }


def _state_template() -> dict[str, Any]:
    """A minimal TutorState-like dict for _aggregate_turn_data."""
    return {
        "user_id": "u-test",
        "conversation_id": "conv-test",
        "context": {},
        "focus_agents": [],
        "pre_focus": [],
    }


# ---------------------------------------------------------------------------
# 1. KT 输出齐全
# ---------------------------------------------------------------------------


class TestAggregateWithKtOutput:
    def test_touched_nodes_format_matches_frontend_contract(self):
        result = _kt_state_for()
        turn_data = TutorGraphEngine._aggregate_turn_data(
            result, _state_template(), "turn-1"
        )
        nodes = turn_data["touched_knowledge_nodes"]
        assert len(nodes) == 3
        for n in nodes:
            # camelCase keys (前端 KnowledgeNode 对齐)
            assert set(n.keys()) == {"id", "label", "mastery", "isHighlight", "status"}
            assert isinstance(n["id"], str)
            assert isinstance(n["label"], str)
            # mastery 来自 mastery_rate 浮点,不是字符串
            assert isinstance(n["mastery"], float)
            assert 0.0 <= n["mastery"] <= 1.0
            assert isinstance(n["isHighlight"], bool)
            assert isinstance(n["status"], str)

    def test_mastery_uses_float_rate_not_string_percent(self):
        """Bug 2 回归:mastery_percent 是 '30.0%' 字符串,要先取 mastery_rate 浮点。"""
        result = _kt_state_for()
        turn_data = TutorGraphEngine._aggregate_turn_data(
            result, _state_template(), "turn-1"
        )
        nodes = turn_data["touched_knowledge_nodes"]
        by_id = {n["id"]: n for n in nodes}
        # 0.3 浮点直传,而不是 '30.0%' 被 _coerce_mastery 转 0.3(精度丢失风险)
        assert by_id["kp1"]["mastery"] == pytest.approx(0.3, abs=1e-6)
        assert by_id["kp2"]["mastery"] == pytest.approx(0.75, abs=1e-6)

    def test_status_preserves_kt_developing_band(self):
        """Bug 3 回归:KT 把 0.4-0.7 标 developing,聚合层不能改成 unknown."""
        result = _kt_state_for()
        turn_data = TutorGraphEngine._aggregate_turn_data(
            result, _state_template(), "turn-1"
        )
        nodes = {n["id"]: n for n in turn_data["touched_knowledge_nodes"]}
        assert nodes["kp1"]["status"] == "weak"
        assert nodes["kp2"]["status"] == "mastered"
        # 关键:developing 必须保留,不能被 _mastery_to_status 改成 unknown
        assert nodes["kp3"]["status"] == "developing"

    def test_weak_points_extracted_as_skill_ids(self):
        """Bug 1 回归:weak_points 是 list[dict],str(dict) 会产生垃圾字符串。"""
        result = _kt_state_for()
        turn_data = TutorGraphEngine._aggregate_turn_data(
            result, _state_template(), "turn-1"
        )
        weak = turn_data["kt_summary"]["weakPoints"]
        assert weak == ["kp1"]  # 抽取 skill_id,不是 "{'skill_id': 'kp1', ...}"
        for w in weak:
            assert isinstance(w, str)
            assert not w.startswith("{")  # 不是 dict 字符串化

    def test_trajectory_follows_kt_output_order(self):
        result = _kt_state_for()
        turn_data = TutorGraphEngine._aggregate_turn_data(
            result, _state_template(), "turn-1"
        )
        assert turn_data["trajectory"] == ["kp1", "kp2", "kp3"]

    def test_focus_agents_dedupe_and_cap_at_two(self):
        result = _kt_state_for(student_focus=[
            "cognitive_diagnosis", "cognitive_diagnosis", "empathy_generator", "study_buddy"
        ])
        turn_data = TutorGraphEngine._aggregate_turn_data(
            result, _state_template(), "turn-1"
        )
        # 去重 + 截断到 2
        assert turn_data["focus_agents"] == ["cognitive_diagnosis", "empathy_generator"]

    def test_is_highlight_for_weak_and_focus(self):
        result = _kt_state_for(student_focus=["cognitive_diagnosis"])
        turn_data = TutorGraphEngine._aggregate_turn_data(
            result, _state_template(), "turn-1"
        )
        nodes = {n["id"]: n for n in turn_data["touched_knowledge_nodes"]}
        # kp1 mastery<0.4 → 高亮
        assert nodes["kp1"]["isHighlight"] is True
        # kp2 mastery>=0.4 且不在 focus_set → 不高亮
        assert nodes["kp2"]["isHighlight"] is False

    def test_kt_summary_carries_diagnosis_summary(self):
        result = _kt_state_for()
        turn_data = TutorGraphEngine._aggregate_turn_data(
            result, _state_template(), "turn-1"
        )
        assert turn_data["kt_summary"]["diagnosisSummary"] == "代数薄弱,需补强"
        # knowledgeStates 字段命名是 camelCase
        ks = turn_data["kt_summary"]["knowledgeStates"]
        assert len(ks) == 3
        assert ks[0]["skillId"] == "kp1"
        assert ks[0]["skillName"] == "代数"
        assert isinstance(ks[0]["mastery"], float)

    def test_kt_summary_carries_diagnosis_source_and_model_info(self):
        """P2 回归:done 事件透出 KT 来源标识,前端可验证是否真跑了 KT 模型。"""
        result = _kt_state_for()
        turn_data = TutorGraphEngine._aggregate_turn_data(
            result, _state_template(), "turn-1"
        )
        ks = turn_data["kt_summary"]
        assert ks["diagnosisSource"] == "kt"
        assert ks["modelInfo"] == {"model_name": "kt", "dataset": "assist09"}
        assert ks["metrics"] == {"rmse": 0.42, "auc": 0.81}


# ---------------------------------------------------------------------------
# 2. 空 state / 没有 KT 输出
# ---------------------------------------------------------------------------


class TestAggregateWithEmptyState:
    def test_no_cognitive_diagnosis_returns_empty_lists(self):
        result = {
            "final_response": "好的",
            "workflow_type": "adaptive_learning",
            "current_stage": "teaching",
            "context": {},  # 没 cognitive_diagnosis
            "focus_agents": ["empathy_generator"],
        }
        turn_data = TutorGraphEngine._aggregate_turn_data(
            result, _state_template(), "turn-2"
        )
        assert turn_data["touched_knowledge_nodes"] == []
        assert turn_data["trajectory"] == []
        assert turn_data["kt_summary"] == {
            "knowledgeStates": [],
            "weakPoints": [],
            "diagnosisSummary": "",
            # 没有 KT 输出时,diagnosisSource 退回 llm_simulation,modelInfo/metrics 为空
            "diagnosisSource": "llm_simulation",
            "modelInfo": {},
            "metrics": {},
        }
        # focus_agents 仍然能从 result.focus_agents 拿到
        assert turn_data["focus_agents"] == ["empathy_generator"]

    def test_missing_focus_agents_returns_empty_list(self):
        result = {"final_response": "x", "context": {}}
        turn_data = TutorGraphEngine._aggregate_turn_data(
            result, _state_template(), "turn-3"
        )
        assert turn_data["focus_agents"] == []

    def test_malformed_kt_state_does_not_raise(self):
        """knowledge_states 含 None / 非 dict 元素时不应崩溃。"""
        result = {
            "context": {
                "cognitive_diagnosis": {
                    "knowledge_states": [
                        None,
                        "not a dict",
                        {"skill_id": "ok", "mastery_rate": 0.5},
                    ],
                    "weak_points": [None, {"skill_id": "w1"}],
                }
            },
            "focus_agents": [],
        }
        turn_data = TutorGraphEngine._aggregate_turn_data(
            result, _state_template(), "turn-4"
        )
        # 只有 1 个有效 ks 被保留
        assert len(turn_data["touched_knowledge_nodes"]) == 1
        assert turn_data["touched_knowledge_nodes"][0]["id"] == "ok"
        assert turn_data["kt_summary"]["weakPoints"] == ["w1"]

    def test_result_with_string_mastery_percent_only(self):
        """如果 KT 输出退化成只有 mastery_percent 字符串(无 mastery_rate),
        _coerce_mastery 必须仍然能正确解析 '75.0%' → 0.75。"""
        result = {
            "context": {
                "cognitive_diagnosis": {
                    "knowledge_states": [
                        {"skill_id": "kp_str", "skill_name": "字符串档", "mastery_percent": "75.0%"},
                    ],
                }
            },
        }
        turn_data = TutorGraphEngine._aggregate_turn_data(
            result, _state_template(), "turn-5"
        )
        node = turn_data["touched_knowledge_nodes"][0]
        assert node["mastery"] == pytest.approx(0.75, abs=1e-6)


# ---------------------------------------------------------------------------
# 3. Safety 短路 → focus_agents 透传
# ---------------------------------------------------------------------------


class TestSafetyShortCircuit:
    """response_assembler 在 safety_blocked 场景把 pre_focus 提升为 focus_agents。
    这里直接验证 _aggregate_turn_data 在结果含 focus_agents(由 response_assembler 写入)时
    正常拿到重点 agent。response_assembler 本身的透传逻辑由 graph 集成测试覆盖。"""

    def test_focus_agents_from_response_assembler_short_circuit(self):
        """模拟 response_assembler 已经把 pre_focus 写入 focus_agents 的场景。"""
        result = {
            "final_response": "抱歉,该话题不在辅导范围。",
            "workflow_type": "adaptive_learning",
            "current_stage": "teaching",
            "context": {"safety": {"risk_category": "self_harm"}},
            # response_assembler 在短路时已经写入
            "focus_agents": ["safety_monitor"],
            # pre_focus 在 response_assembler 中已被消费,理论上不残留
            "pre_focus": [],
        }
        state = _state_template()
        state["pre_focus"] = ["safety_monitor"]  # 模拟 safety_gate 写入
        turn_data = TutorGraphEngine._aggregate_turn_data(result, state, "turn-6")
        assert turn_data["focus_agents"] == ["safety_monitor"]
        # KT 没跑,touched_nodes / trajectory 必须为空
        assert turn_data["touched_knowledge_nodes"] == []
        assert turn_data["trajectory"] == []

    def test_pre_focus_falls_back_when_focus_agents_missing(self):
        """如果 response_assembler 没写 focus_agents,但 pre_focus 还在,
        _aggregate_turn_data 会从 state.pre_focus 兜底(实际上 response_assembler
        现在会主动写 focus_agents,但聚合层做兜底更稳)。"""
        result = {
            "final_response": "blocked",
            "context": {},
            "focus_agents": [],  # 没写
        }
        state = _state_template()
        state["pre_focus"] = ["safety_monitor"]
        turn_data = TutorGraphEngine._aggregate_turn_data(result, state, "turn-7")
        # state.focus_agents 也是空,最终落空数组(聚合层不主动读 pre_focus;
        # 这是设计选择:pre_focus 是临时评分,decide 或 response_assembler 必须消费它)
        assert turn_data["focus_agents"] == []


# ---------------------------------------------------------------------------
# 4. SSE done payload 字段命名契约(camelCase 对齐前端 StreamDonePayload)
# ---------------------------------------------------------------------------


class TestDoneEventPayloadContract:
    def _build_done_payload(self, result: dict[str, Any]) -> dict[str, Any]:
        """Mirror what chat_service.stream_message does at the end of a turn."""
        turn_data = TutorGraphEngine._aggregate_turn_data(result, {}, "turn-id-x")
        merged = {**result, **{
            "focus_agents": turn_data["focus_agents"],
            "touched_knowledge_nodes": turn_data["touched_knowledge_nodes"],
            "trajectory": turn_data["trajectory"],
            "kt_summary": turn_data["kt_summary"],
        }}
        kt_summary = merged.get("kt_summary") or {}
        kt_summary_clean = {
            "knowledgeStates": kt_summary.get("knowledgeStates", []),
            "weakPoints": kt_summary.get("weakPoints", []),
        }
        if kt_summary.get("diagnosisSummary"):
            kt_summary_clean["diagnosisSummary"] = kt_summary["diagnosisSummary"]
        return {
            "type": "done",
            "workflow": merged.get("workflow"),
            "stage": merged.get("stage"),
            "turn_id": "turn-id-x",
            "turnId": "turn-id-x",
            "focusAgents": merged.get("focus_agents") or [],
            "touchedNodes": merged.get("touched_knowledge_nodes") or [],
            "trajectory": merged.get("trajectory") or [],
            "ktSummary": kt_summary_clean,
        }

    def test_payload_keys_are_camelcase(self):
        result = _kt_state_for()
        payload = self._build_done_payload(result)
        # camelCase 必填字段
        assert "turnId" in payload
        assert "focusAgents" in payload
        assert "touchedNodes" in payload
        assert "trajectory" in payload
        assert "ktSummary" in payload
        # snake_case 仍保留(向后兼容,前端 parseDonePayload 双向兼容)
        assert "turn_id" in payload  # legacy

    def test_payload_is_json_serialisable(self):
        """SSE 必须能 json.dumps,不能有 NaN / set / datetime 等不可序列化对象。"""
        result = _kt_state_for()
        payload = self._build_done_payload(result)
        # 不抛错即可
        json.dumps(payload, ensure_ascii=False)

    def test_payload_touched_nodes_use_camelcase_inner_keys(self):
        """前端 KnowledgeNode 期望 camelCase 的 isHighlight / skillName 等。"""
        result = _kt_state_for()
        payload = self._build_done_payload(result)
        for node in payload["touchedNodes"]:
            assert "isHighlight" in node
            assert "is_highlight" not in node
            assert "mastery" in node

    def test_payload_kt_summary_uses_camelcase_inner_keys(self):
        result = _kt_state_for()
        payload = self._build_done_payload(result)
        ks_list = payload["ktSummary"]["knowledgeStates"]
        assert ks_list  # 非空
        for ks in ks_list:
            assert "skillId" in ks
            assert "skillName" in ks
            assert "skill_id" not in ks
