from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import threading
import time
from typing import Any, Iterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from chat_agent.main import build_chat_runtime
from chat_agent.models import OrchestrationResult, SkillDefinition
from chat_agent.session import ChatSession


WEB_DIR = Path(__file__).resolve().parents[1] / "web"


class MessageRequest(BaseModel):
    message: str


def create_app(orchestrator=None, skills: list[SkillDefinition] | None = None) -> FastAPI:
    if orchestrator is None or skills is None:
        orchestrator, skills, _config = build_chat_runtime()

    app = FastAPI(title="ChatAgent", version="0.1.0")
    app.state.orchestrator = orchestrator
    app.state.skills = skills
    app.state.sessions: dict[str, ChatSession] = {}

    if WEB_DIR.exists():
        app.mount("/web", StaticFiles(directory=str(WEB_DIR)), name="web")

    @app.get("/")
    def index():
        return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-store"})

    @app.get("/api/health")
    def health():
        return {"status": "ok", "sessions": len(app.state.sessions), "skills": len(app.state.skills)}

    @app.get("/api/skills")
    def list_skills():
        return [_skill_to_dict(skill) for skill in app.state.skills]

    @app.post("/api/sessions")
    def create_session():
        session = ChatSession()
        app.state.sessions[session.session_id] = session
        return {"session_id": session.session_id, "session": _session_to_dict(session)}

    @app.get("/api/sessions/{session_id}")
    def get_session(session_id: str):
        session = _get_session(app, session_id)
        return {"session_id": session.session_id, "session": _session_to_dict(session)}

    @app.post("/api/sessions/{session_id}/messages/stream")
    def send_message_stream(session_id: str, request: MessageRequest):
        session = _get_session(app, session_id)
        message = request.message.strip()
        if not message:
            raise HTTPException(status_code=400, detail="message is required")

        return StreamingResponse(
            _stream_message(app, session, message),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    return app


def _get_session(app: FastAPI, session_id: str) -> ChatSession:
    try:
        return app.state.sessions[session_id]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc


def _skill_to_dict(skill: SkillDefinition) -> dict[str, Any]:
    return {
        "name": skill.name,
        "description": skill.description,
        "level": skill.level,
        "executor_name": skill.executor_name,
        "path": str(skill.path) if skill.path is not None else None,
    }


def _session_to_dict(session: ChatSession) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "messages": [asdict(message) for message in session.messages],
        "slots": dict(session.slots),
        "pending_skill": session.pending_skill,
        "pending_inputs": list(session.pending_inputs),
        "last_result": _result_to_dict(session.last_result) if session.last_result else None,
        "events": [asdict(event) for event in session.events],
    }


def _result_to_dict(result: OrchestrationResult) -> dict[str, Any]:
    return asdict(result)


def _stream_message(app: FastAPI, session: ChatSession, message: str) -> Iterator[str]:
    event_index = len(session.events)
    done = threading.Event()
    result_holder: dict[str, OrchestrationResult] = {}
    error_holder: dict[str, BaseException] = {}

    def run_orchestrator() -> None:
        try:
            result_holder["result"] = app.state.orchestrator.handle_message(message, session=session)
        except BaseException as exc:  # pragma: no cover - exercised through streaming error path.
            error_holder["error"] = exc
        finally:
            done.set()

    worker = threading.Thread(target=run_orchestrator, daemon=True)
    worker.start()

    yield _sse_event("status", {"status": "running"})

    while not done.is_set() or event_index < len(session.events):
        while event_index < len(session.events):
            yield _sse_event("event", {"event": asdict(session.events[event_index])})
            event_index += 1
        if not done.is_set():
            time.sleep(0.05)

    worker.join()

    if error_holder:
        error = error_holder["error"]
        yield _sse_event("error", {"message": str(error) or error.__class__.__name__})
        yield _sse_event("done", {"status": "error"})
        return

    result = result_holder["result"]
    for chunk in _text_chunks(result.final_response):
        yield _sse_event("assistant_delta", {"content": chunk})

    yield _sse_event(
        "session",
        {
            "session_id": session.session_id,
            "result": _result_to_dict(result),
            "session": _session_to_dict(session),
        },
    )
    yield _sse_event("done", {"status": result.status})


def _sse_event(name: str, payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {name}\ndata: {data}\n\n"


def _text_chunks(text: str, size: int = 24) -> Iterator[str]:
    for index in range(0, len(text), size):
        yield text[index : index + size]


app = create_app()
