import json

from chat_agent.models import OrchestrationResult, SkillDefinition, SkillPolicy
from chat_agent.server import create_app
from fastapi.testclient import TestClient


class FakeOrchestrator:
    def handle_message(self, message, session=None):
        if session is not None:
            session.add_message("user", message)
            session.add_event("message_received", "收到用户消息。", user_message=message)
            if "学生" not in message and "5" not in message:
                session.pending_skill = "kt-runtime-skill"
                session.pending_inputs = ["student_id"]
                response = "请补充学生 ID。"
                session.add_message("assistant", response)
                return OrchestrationResult(
                    status="need_input",
                    final_response=response,
                    skill_name="kt-runtime-skill",
                    raw_result=None,
                    missing_inputs=["student_id"],
                )
            session.slots["student_id"] = "5"
            session.clear_pending()
            session.add_event("workflow_finished", "工作流执行完成。", status="ok")
            response = "报告正文"
            session.add_message("assistant", response)
            return OrchestrationResult(
                status="ok",
                final_response=response,
                skill_name="kt-runtime-skill",
                raw_result={"ok": True},
                missing_inputs=[],
            )
        raise AssertionError("session is required")


def fake_skill():
    return SkillDefinition(
        name="kt-runtime-skill",
        description="KT",
        path=None,
        instructions="",
        policy=SkillPolicy(),
        level=1,
        executor_name="skill_markdown",
    )


def parse_sse_events(text):
    events = []
    for block in text.strip().split("\n\n"):
        name = None
        data_lines = []
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data_lines.append(line.removeprefix("data: "))
        if name:
            events.append((name, json.loads("\n".join(data_lines))))
    return events


def stream_message(client, session_id, message):
    with client.stream(
        "POST",
        f"/api/sessions/{session_id}/messages/stream",
        json={"message": message},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        return parse_sse_events(response.read().decode())


def latest_payload(events, name):
    for event_name, payload in reversed(events):
        if event_name == name:
            return payload
    raise AssertionError(f"missing SSE event: {name}")


def test_server_creates_session_and_runs_with_student_id_only():
    app = create_app(orchestrator=FakeOrchestrator(), skills=[fake_skill()])
    client = TestClient(app)

    created = client.post("/api/sessions").json()
    session_id = created["session_id"]

    first = latest_payload(stream_message(client, session_id, "帮学生 5 做 KT 学情分析"), "session")

    assert first["result"]["status"] == "ok"
    assert first["session"]["pending_skill"] is None
    assert first["session"]["slots"]["student_id"] == "5"
    assert first["result"]["final_response"] == "报告正文"


def test_server_streams_message_response_and_session_updates():
    app = create_app(orchestrator=FakeOrchestrator(), skills=[fake_skill()])
    client = TestClient(app)
    session_id = client.post("/api/sessions").json()["session_id"]

    events = stream_message(client, session_id, "帮学生 5 做 KT 学情分析。")
    names = [name for name, _payload in events]
    session_payload = latest_payload(events, "session")

    assert names[:2] == ["status", "event"]
    assert "assistant_delta" in names
    assert names[-2:] == ["session", "done"]
    assert latest_payload(events, "done")["status"] == "ok"
    assert session_payload["result"]["final_response"] == "报告正文"
    assert session_payload["session"]["messages"][-2:] == [
        {"role": "user", "content": "帮学生 5 做 KT 学情分析。"},
        {"role": "assistant", "content": "报告正文"},
    ]


def test_server_exposes_skills_and_index_page():
    app = create_app(orchestrator=FakeOrchestrator(), skills=[fake_skill()])
    client = TestClient(app)

    skills = client.get("/api/skills").json()
    index = client.get("/")

    assert skills[0]["name"] == "kt-runtime-skill"
    assert index.status_code == 200
    assert index.headers["cache-control"] == "no-store"
    assert "ChatAgent" in index.text
    assert 'src="/web/app.js?v=' in index.text
