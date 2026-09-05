import json

import pytest

from agent.cerebras_responder import CerebrasResponder


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


def test_cerebras_responder_builds_structured_request():
    captured = {}

    def opener(req, timeout):
        captured["request"] = req
        captured["timeout"] = timeout
        return _Response({"choices": [{"message": {"content": json.dumps({"action_type": "tap", "target_id": "target", "value": None, "reason": "advance"})}}]})

    responder = CerebrasResponder(api_key="test-key", model="test-model", timeout_seconds=7, opener=opener)
    result = responder('{"goal":"Tap target"}')

    assert result["target_id"] == "target"
    assert captured["timeout"] == 7
    assert captured["request"].full_url == "https://api.cerebras.ai/v1/chat/completions"
    assert captured["request"].get_header("Authorization") == "Bearer test-key"
    body = json.loads(captured["request"].data.decode("utf-8"))
    assert body["model"] == "test-model"
    assert body["temperature"] == 0
    assert body["max_completion_tokens"] == 256
    assert body["stream"] is False
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True


def test_cerebras_responder_requires_api_key():
    with pytest.raises(RuntimeError, match="CEREBRAS_API_KEY is not set"):
        CerebrasResponder(api_key="")("{}")


def test_cerebras_responder_rejects_blank_prompt():
    with pytest.raises(ValueError, match="prompt must not be blank"):
        CerebrasResponder(api_key="test-key")("   ")


def test_cerebras_responder_does_not_retry_timeout():
    calls = 0

    def opener(req, timeout):
        nonlocal calls
        calls += 1
        raise TimeoutError()

    with pytest.raises(RuntimeError, match="timed out"):
        CerebrasResponder(api_key="test-key", opener=opener)("{}")

    assert calls == 1
