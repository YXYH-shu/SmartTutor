from langchain_core.messages import AIMessage

from chat_agent.deep_agent import DeepAgentRuntime, _llm
from chat_agent.models import SkillDefinition, SkillExecutionResult, SkillPolicy
from chat_agent.session import ChatSession


class FakeRegistry:
    def run_skill(self, skill_name, inputs, session=None):
        raise AssertionError("not used in this test")


class FakeOrchestrator:
    registry = FakeRegistry()

    class validator:
        @staticmethod
        def validate(**_kwargs):
            return None


def skill():
    return SkillDefinition(
        name="kt-runtime-skill",
        description="Use when 需要基于学生 ID 运行 KT 预测。",
        path=None,
        instructions="",
        policy=SkillPolicy(
            default_entrypoints=["conda run -n kt python scripts/run_kt.py"],
            required_inputs=["student_id"],
            output_paths=["llm_analysis.report_markdown"],
        ),
        level=1,
        executor_name="skill_markdown",
    )


def test_deep_agent_runtime_exposes_generic_skill_tool(monkeypatch):
    captured = {}

    def fake_create_deep_agent(**kwargs):
        captured.update(kwargs)
        return {"agent": "fake"}

    monkeypatch.setattr("chat_agent.deep_agent.create_deep_agent", fake_create_deep_agent)
    monkeypatch.setattr("chat_agent.deep_agent._llm", lambda: "fake-model")
    runtime = DeepAgentRuntime(orchestrator=FakeOrchestrator(), skills=[skill()], config={})

    agent = runtime._build_agent(ChatSession())

    assert agent == {"agent": "fake"}
    tool_names = [tool.__name__ for tool in captured["tools"]]
    assert tool_names == ["run_skill"]
    assert "run_kt_analysis" not in captured["system_prompt"]
    assert "run_skill" in captured["system_prompt"]
    assert "只能根据 skill description 判断是否调用 skill" in captured["system_prompt"]
    assert "AGENT_REWRITE_REQUIRED" in captured["system_prompt"]
    assert "根据上下文判断是否需要调用已注册 skill" not in captured["system_prompt"]


def test_llm_default_timeout_is_120_seconds(monkeypatch):
    monkeypatch.setenv("CHATAGENT_LLM_BASE_URL", "http://llm.test/v1")
    monkeypatch.setenv("CHATAGENT_LLM_API_KEY", "key")
    monkeypatch.setenv("CHATAGENT_LLM_MODEL", "model")
    monkeypatch.delenv("CHATAGENT_LLM_TIMEOUT", raising=False)

    assert _llm().timeout == 120


def test_deep_agent_runtime_propagates_agent_errors(monkeypatch):
    class ExplodingAgent:
        def invoke(self, _payload):
            raise RuntimeError("boom")

    monkeypatch.setattr("chat_agent.deep_agent.create_deep_agent", lambda **_kwargs: ExplodingAgent())
    monkeypatch.setattr("chat_agent.deep_agent._llm", lambda: "fake-model")
    monkeypatch.setattr("chat_agent.deep_agent._llm_base_url", lambda: "http://llm.test/v1")
    monkeypatch.setattr("chat_agent.deep_agent._llm_api_key", lambda: "key")
    monkeypatch.setattr("chat_agent.deep_agent._llm_model", lambda: "model")
    runtime = DeepAgentRuntime(orchestrator=FakeOrchestrator(), skills=[skill()], config={})

    try:
        runtime.handle_message("帮学生 5 做 KT 学情分析。", session=ChatSession())
    except RuntimeError as exc:
        assert str(exc) == "boom"
    else:
        raise AssertionError("DeepAgent errors must propagate to the SSE error path")


def test_deep_agent_runtime_raises_when_llm_is_not_configured(monkeypatch):
    monkeypatch.setattr("chat_agent.deep_agent._llm_base_url", lambda: "")
    monkeypatch.setattr("chat_agent.deep_agent._llm_api_key", lambda: "")
    monkeypatch.setattr("chat_agent.deep_agent._llm_model", lambda: "")
    runtime = DeepAgentRuntime(orchestrator=FakeOrchestrator(), skills=[skill()], config={})

    try:
        runtime.handle_message("帮学生 5 做 KT 学情分析。", session=ChatSession())
    except RuntimeError as exc:
        assert "DeepAgent LLM is not configured" in str(exc)
    else:
        raise AssertionError("Missing LLM configuration must propagate to the error path")


def test_deep_agent_runtime_sends_session_history_to_llm(monkeypatch):
    captured_payloads = []

    class RecordingAgent:
        def invoke(self, payload):
            captured_payloads.append(payload)
            return {"messages": [payload["messages"][-1], AIMessage(content="收到")]}

    monkeypatch.setattr("chat_agent.deep_agent.create_deep_agent", lambda **_kwargs: RecordingAgent())
    monkeypatch.setattr("chat_agent.deep_agent._llm", lambda: "fake-model")
    monkeypatch.setattr("chat_agent.deep_agent._llm_base_url", lambda: "http://llm.test/v1")
    monkeypatch.setattr("chat_agent.deep_agent._llm_api_key", lambda: "key")
    monkeypatch.setattr("chat_agent.deep_agent._llm_model", lambda: "model")
    runtime = DeepAgentRuntime(orchestrator=FakeOrchestrator(), skills=[skill()], config={})
    session = ChatSession()

    runtime.handle_message("我最近在学电路。", session=session)
    runtime.handle_message("闭合回路为什么才能让小灯泡亮？", session=session)

    second_turn_messages = captured_payloads[1]["messages"]
    assert [message.content for message in second_turn_messages] == [
        "我最近在学电路。",
        "收到",
        "闭合回路为什么才能让小灯泡亮？",
    ]


def test_run_skill_adds_recent_learning_context_for_kt_skill():
    captured = {}

    class RecordingRegistry:
        def run_skill(self, skill_name, inputs, session=None):
            captured["skill_name"] = skill_name
            captured["inputs"] = dict(inputs)
            return SkillExecutionResult(
                skill_name=skill_name,
                executor_name="skill_markdown",
                raw_json={"status": "ok"},
                report_markdown="报告",
                predictions=[],
                metrics={},
                command_results=[],
            )

        def get_skill(self, _skill_name):
            return skill()

    class RecordingOrchestrator:
        registry = RecordingRegistry()
        validator = FakeOrchestrator.validator

    session = ChatSession()
    session.add_message("user", "你好，我是学生 ID 40 的学生。你可以帮我学习科学和数学吗？")
    session.add_message("assistant", "可以。")
    session.add_message("user", "我最近在学电路，闭合回路为什么才能让小灯泡亮起来？")
    session.add_message("assistant", "闭合回路可以让电流持续流动。")
    session.add_message("user", "请帮我做一个学情分析，看看我现在的学习情况。")
    runtime = DeepAgentRuntime(orchestrator=RecordingOrchestrator(), skills=[skill()], config={})

    runtime._run_skill_tool(session)("kt-runtime-skill", {"student_id": "40"})

    assert captured["skill_name"] == "kt-runtime-skill"
    assert captured["inputs"]["student_id"] == "40"
    assert "闭合回路" in captured["inputs"]["history_context"]
    assert "学情分析" not in captured["inputs"]["history_context"]


def test_run_skill_combines_explicit_history_context_with_recent_learning_context():
    captured = {}

    class RecordingRegistry:
        def run_skill(self, skill_name, inputs, session=None):
            captured["inputs"] = dict(inputs)
            return SkillExecutionResult(
                skill_name=skill_name,
                executor_name="skill_markdown",
                raw_json={"status": "ok"},
                report_markdown="报告",
                predictions=[],
                metrics={},
                command_results=[],
            )

        def get_skill(self, _skill_name):
            return skill()

    class RecordingOrchestrator:
        registry = RecordingRegistry()
        validator = FakeOrchestrator.validator

    session = ChatSession()
    session.add_message("user", "我最近在学电路。")
    runtime = DeepAgentRuntime(orchestrator=RecordingOrchestrator(), skills=[skill()], config={})

    runtime._run_skill_tool(session)("kt-runtime-skill", {"student_id": "40", "history_context": "显式上下文"})

    assert "我最近在学电路。" in captured["inputs"]["history_context"]
    assert "显式上下文" in captured["inputs"]["history_context"]


def test_run_skill_tool_returns_report_markdown_without_raw_predictions():
    class RecordingRegistry:
        def run_skill(self, skill_name, inputs, session=None):
            return SkillExecutionResult(
                skill_name=skill_name,
                executor_name="skill_markdown",
                raw_json={
                    "status": "ok",
                    "predictions": [{"skill_id": index} for index in range(334)],
                    "llm_analysis": {"report_markdown": "报告底稿"},
                },
                report_markdown="报告底稿",
                predictions=[{"skill_id": index} for index in range(334)],
                metrics={"num_predictions": 334},
                command_results=[],
            )

        def get_skill(self, _skill_name):
            return skill()

    class RecordingOrchestrator:
        registry = RecordingRegistry()
        validator = FakeOrchestrator.validator

    session = ChatSession()
    session.add_message("user", "我最近在学电路，闭合回路为什么才能让小灯泡亮起来？")
    session.add_message("assistant", "闭合回路可以让电流持续流动。")
    runtime = DeepAgentRuntime(orchestrator=RecordingOrchestrator(), skills=[skill()], config={})

    payload = runtime._run_skill_tool(session)("kt-runtime-skill", {"student_id": "42"})

    assert payload == {
        "status": "ok",
        "skill_name": "kt-runtime-skill",
        "report_markdown": "报告底稿",
        "user_question_context": "我最近在学电路，闭合回路为什么才能让小灯泡亮起来？",
    }
    assert "raw_result" not in payload
    assert "predictions" not in payload


def test_kt_skill_agent_rewrite_block_is_assembled_into_full_report(monkeypatch):
    marker_report = (
        "## 1. 主题判定\n\n"
        "主题判定原文。\n\n"
        "## 2. 知识点集合\n\n"
        "| 知识点ID | 知识点名称 |\n"
        "|------------|------------|\n"
        "| KP052 | 导体与绝缘体 |\n\n"
        "## 3. 学情分析结果\n\n"
        "自然语言分析\n\n"
        "<!-- AGENT_REWRITE_REQUIRED_BEGIN -->内部写作任务<!-- AGENT_REWRITE_REQUIRED_END -->\n\n"
        "| 知识点ID | 预测掌握度 |\n"
        "|------------|------------|\n"
        "| KP052 | 80.97% |\n\n"
        "## 4. 诊断知识点明细\n\n"
        "选中知识点明细原文。"
    )

    class RecordingRegistry:
        def run_skill(self, skill_name, inputs, session=None):
            return SkillExecutionResult(
                skill_name=skill_name,
                executor_name="skill_markdown",
                raw_json={
                    "status": "ok",
                    "llm_analysis": {
                        "report_markdown": marker_report,
                        "agent_revision_task": {
                            "source_materials": {
                                "weak_points": [
                                    {
                                        "knowledge_point_name": "电路基本元件",
                                        "predicted_mastery": "28.77%",
                                    }
                                ]
                            }
                        },
                    },
                },
                report_markdown=marker_report,
                predictions=[],
                metrics={},
                command_results=[],
            )

        def get_skill(self, _skill_name):
            return skill()

    class RecordingOrchestrator:
        registry = RecordingRegistry()
        validator = FakeOrchestrator.validator

    class RewritingAgent:
        def __init__(self, tool):
            self.tool = tool

        def invoke(self, _payload):
            self.tool("kt-runtime-skill", {"student_id": "40"})
            return {
                "messages": [
                    AIMessage(
                        content=(
                            "以下是学生 40 的学情分析报告，其中自然语言分析与教学建议部分已根据模型预测数据重新撰写：\n\n"
                            "---\n\n"
                            "## 3. 学情分析结果\n\n"
                            "自然语言分析\n\n"
                            "根据返回的 KT 诊断结果，以下是替换后的自然语言分析与教学建议：\n\n"
                            "### 3.1 总体学情概述\n\n"
                            "整体学情画像：已由 Agent 重写。\n\n"
                            "| 知识点ID | 预测掌握度 |\n"
                            "|------------|------------|\n"
                            "| KP052 | 80.97% |\n\n"
                            "---\n\n"
                            "以上自然语言分析和教学建议已根据模型预测数据生成。报告其余部分保持不变。"
                        )
                    )
                ]
            }

    def fake_create_deep_agent(**kwargs):
        return RewritingAgent(kwargs["tools"][0])

    monkeypatch.setattr("chat_agent.deep_agent.create_deep_agent", fake_create_deep_agent)
    monkeypatch.setattr("chat_agent.deep_agent._llm", lambda: "fake-model")
    monkeypatch.setattr("chat_agent.deep_agent._llm_base_url", lambda: "http://llm.test/v1")
    monkeypatch.setattr("chat_agent.deep_agent._llm_api_key", lambda: "key")
    monkeypatch.setattr("chat_agent.deep_agent._llm_model", lambda: "model")

    runtime = DeepAgentRuntime(orchestrator=RecordingOrchestrator(), skills=[skill()], config={})
    result = runtime.handle_message("请帮学生 40 做学情分析。", session=ChatSession())

    assert result.final_response == (
        "## 1. 主题判定\n\n"
        "主题判定原文。\n\n"
        "## 2. 知识点集合\n\n"
        "| 知识点ID | 知识点名称 |\n"
        "|------------|------------|\n"
        "| KP052 | 导体与绝缘体 |\n\n"
        "## 3. 学情分析结果\n\n"
        "自然语言分析\n\n"
        "### 3.1 总体学情概述\n\n"
        "整体学情画像：已由 Agent 重写。\n\n"
        "| 知识点ID | 预测掌握度 |\n"
        "|------------|------------|\n"
        "| KP052 | 80.97% |\n\n"
        "## 4. 诊断知识点明细\n\n"
        "选中知识点明细原文。"
    )
    assert "AGENT_REWRITE_REQUIRED" not in result.final_response
    assert "以下是学生" not in result.final_response
    assert "根据返回的 KT 诊断结果" not in result.final_response
    assert "以上自然语言分析" not in result.final_response
    assert "\n---\n" not in result.final_response


def test_kt_skill_complete_agent_report_is_used_as_is(monkeypatch):
    marker_report = (
        "## 1. 主题判定\n\n"
        "底稿主题。\n\n"
        "## 2. 知识点集合\n\n"
        "底稿知识点。\n\n"
        "## 3. 学情分析结果\n\n"
        "<!-- AGENT_REWRITE_REQUIRED_BEGIN -->内部写作任务<!-- AGENT_REWRITE_REQUIRED_END -->\n\n"
        "## 4. 诊断知识点明细\n\n"
        "底稿明细。"
    )
    complete_report = (
        "## 1. 主题判定\n\n"
        "Agent 主题。\n\n"
        "## 2. 知识点集合\n\n"
        "Agent 知识点。\n\n"
        "## 3. 学情分析结果\n\n"
        "Agent 学情分析。\n\n"
        "## 4. 诊断知识点明细\n\n"
        "Agent 明细。"
    )

    class RecordingRegistry:
        def run_skill(self, skill_name, inputs, session=None):
            return SkillExecutionResult(
                skill_name=skill_name,
                executor_name="skill_markdown",
                raw_json={"status": "ok", "llm_analysis": {"report_markdown": marker_report}},
                report_markdown=marker_report,
                predictions=[],
                metrics={},
                command_results=[],
            )

        def get_skill(self, _skill_name):
            return skill()

    class RecordingOrchestrator:
        registry = RecordingRegistry()
        validator = FakeOrchestrator.validator

    class CompleteReportAgent:
        def __init__(self, tool):
            self.tool = tool

        def invoke(self, _payload):
            self.tool("kt-runtime-skill", {"student_id": "40"})
            return {"messages": [AIMessage(content=complete_report)]}

    monkeypatch.setattr("chat_agent.deep_agent.create_deep_agent", lambda **kwargs: CompleteReportAgent(kwargs["tools"][0]))
    monkeypatch.setattr("chat_agent.deep_agent._llm", lambda: "fake-model")
    monkeypatch.setattr("chat_agent.deep_agent._llm_base_url", lambda: "http://llm.test/v1")
    monkeypatch.setattr("chat_agent.deep_agent._llm_api_key", lambda: "key")
    monkeypatch.setattr("chat_agent.deep_agent._llm_model", lambda: "model")

    runtime = DeepAgentRuntime(orchestrator=RecordingOrchestrator(), skills=[skill()], config={})
    result = runtime.handle_message("请帮学生 40 做学情分析。", session=ChatSession())

    assert result.final_response == complete_report
