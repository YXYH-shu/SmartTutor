import json

from langchain_core.messages import HumanMessage

from chat_agent.llm import OpenAICompatibleChatModel


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "model": "fake-model",
            "choices": [
                {
                    "message": {"content": "ok"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }


class FakeClient:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def post(self, *args, **kwargs):
        return FakeResponse()


def test_llm_context_log_records_request_payload_without_api_key(monkeypatch, tmp_path):
    log_path = tmp_path / "llm_context.jsonl"
    monkeypatch.setenv("CHATAGENT_LLM_CONTEXT_LOG", str(log_path))
    monkeypatch.setattr("chat_agent.llm.httpx.Client", FakeClient)

    model = OpenAICompatibleChatModel(
        model="fake-model",
        base_url="http://llm.test/v1",
        api_key="secret-key",
    )

    model.invoke([HumanMessage(content="帮学生 5 做 KT 学情分析。")])

    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["model"] == "fake-model"
    assert rows[0]["base_url"] == "http://llm.test/v1"
    assert rows[0]["payload"]["messages"][0]["content"] == "帮学生 5 做 KT 学情分析。"
    assert "secret-key" not in log_path.read_text(encoding="utf-8")
