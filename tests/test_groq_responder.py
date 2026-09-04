import json

import pytest

from agent.groq_responder import GroqResponder


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


def test_groq_responder_builds_bounded_structured_request():
    captured = {}

    def opener(req, timeout):
        captured["request"] = req
        captured["timeout"] = timeout
        return _Response(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "action_type": "tap",
                                    "target_id": "target",
                                    "value": None,
                                    "reason": "select visible target",
                                }
                            )
                        }
                    }
                ]
            }
        )

    responder = GroqResponder(api_key="test-key", model="test-model", timeout_seconds=7, opener=opener)
    result = responder('{"goal":"Tap target"}')

    assert result["action_type"] == "tap"
    assert result["target_id"] == "target"
    assert captured["timeout"] == 7
    assert captured["request"].full_url == "https://api.groq.com/openai/v1/chat/completions"
    assert captured["request"].get_header("Authorization") == "Bearer test-key"
    body = json.loads(captured["request"].data.decode("utf-8"))
    assert body["model"] == "test-model"
    assert body["temperature"] == 0
    assert body["max_completion_tokens"] == 256
    assert body["stream"] is False
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True


def test_groq_responder_requires_api_key():
    with pytest.raises(RuntimeError, match="GROQ_API_KEY is not set"):
        GroqResponder(api_key="")("{}")


def test_groq_responder_rejects_blank_prompt():
    with pytest.raises(ValueError, match="prompt must not be blank"):
        GroqResponder(api_key="test-key")("   ")


def test_groq_responder_does_not_retry_http_failure():
    calls = 0

    def opener(req, timeout):
        nonlocal calls
        calls += 1
        raise TimeoutError()

    with pytest.raises(RuntimeError, match="timed out"):
        GroqResponder(api_key="test-key", opener=opener)("{}")

    assert calls == 1
