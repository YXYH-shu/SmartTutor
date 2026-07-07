from chat_agent.deep_agent import ChatAgentTools, create_chat_deep_agent
from chat_agent.models import OrchestrationResult, SkillDefinition, SkillPolicy


class FakeOrchestrator:
    def handle_message(self, message, session=None):
        if session is not None:
            session.add_message("user", message)
        return OrchestrationResult(
            status="ok",
            final_response=f"handled: {message}",
            skill_name="kt-runtime-skill",
            raw_result={"ok": True},
            missing_inputs=[],
        )


def test_chat_agent_tools_expose_workflow_as_plain_functions():
    tools = ChatAgentTools(orchestrator=FakeOrchestrator(), skills=[])

    result = tools.run_workflow("帮学生 5 做学情分析", session_id="s1")

    assert result["status"] == "ok"
    assert result["final_response"] == "handled: 帮学生 5 做学情分析"
    assert result["session_id"] == tools.sessions["s1"].session_id
    assert tools.list_sessions()[0]["message_count"] == 1


def test_create_chat_deep_agent_passes_tools_and_skill_sources(monkeypatch):
    captured = {}

    def fake_create_deep_agent(**kwargs):
        captured.update(kwargs)
        return {"agent": "fake"}

    monkeypatch.setattr("chat_agent.deep_agent.create_deep_agent", fake_create_deep_agent)
    skill = SkillDefinition(
        name="kt-runtime-skill",
        description="KT",
        path=None,
        instructions="",
        policy=SkillPolicy(),
        level=1,
        executor_name="skill_markdown",
    )

    agent = create_chat_deep_agent(
        orchestrator=FakeOrchestrator(),
        skills=[skill],
        model="openai:gpt-5-mini",
        skill_sources=["/home/duanzt/skills"],
    )

    assert agent == {"agent": "fake"}
    assert captured["model"] == "openai:gpt-5-mini"
    assert captured["skills"] == ["/home/duanzt/skills"]
    tool_names = {tool.__name__ for tool in captured["tools"]}
    assert {"list_skills", "list_sessions", "run_workflow", "run_skill"} <= tool_names
