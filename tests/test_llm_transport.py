import json
from urllib.error import HTTPError, URLError

import pytest

from agent.llm_transport import LLMTransportError, OpenAICompatibleTransport


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.payload


def test_transport_posts_prompt_and_returns_structured_json(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["authorization"] = request.headers.get("Authorization")
        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"action_type":"click","target":{"element_id":"n1"}}'
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("agent.llm_transport.urlopen", fake_urlopen)

    result = OpenAICompatibleTransport(
        "http://127.0.0.1:8080",
        "qwen-test",
        timeout=7.0,
        api_key="local-key",
    ).complete("reason about this UI")

    assert result["action_type"] == "click"
    assert captured["url"] == "http://127.0.0.1:8080/v1/chat/completions"
    assert captured["timeout"] == 7.0
    assert captured["body"]["model"] == "qwen-test"
    assert captured["body"]["messages"] == [
        {"role": "user", "content": "reason about this UI"}
    ]
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert captured["authorization"] == "Bearer local-key"


def test_transport_allows_local_server_without_api_key(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["authorization"] = request.headers.get("Authorization")
        return FakeResponse(
            {
                "choices": [
                    {"message": {"content": '{"action_type":"wait"}'}},
                ]
            }
        )

    monkeypatch.setattr("agent.llm_transport.urlopen", fake_urlopen)

    result = OpenAICompatibleTransport("http://localhost:8080", "local").complete("wait")

    assert result == {"action_type": "wait"}
    assert captured["authorization"] is None


def test_transport_wraps_connection_failure(monkeypatch):
    def fake_urlopen(request, timeout):
        raise URLError("connection refused")

    monkeypatch.setattr("agent.llm_transport.urlopen", fake_urlopen)

    with pytest.raises(LLMTransportError, match="connection failed"):
        OpenAICompatibleTransport("http://localhost:8080", "local").complete("test")


def test_transport_wraps_http_failure(monkeypatch):
    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 503, "unavailable", {}, None)

    monkeypatch.setattr("agent.llm_transport.urlopen", fake_urlopen)

    with pytest.raises(LLMTransportError, match="HTTP error: 503"):
        OpenAICompatibleTransport("http://localhost:8080", "local").complete("test")


def test_transport_rejects_non_json_model_message(monkeypatch):
    def fake_urlopen(request, timeout):
        return FakeResponse(
            {"choices": [{"message": {"content": "not json"}}]}
        )

    monkeypatch.setattr("agent.llm_transport.urlopen", fake_urlopen)

    with pytest.raises(LLMTransportError, match="not valid JSON"):
        OpenAICompatibleTransport("http://localhost:8080", "local").complete("test")
