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
    assert captured["request"].get_header("User-agent") == "Nova-Agent/1.0"
    assert captured["request"].get_header("Accept") == "application/json"
    body = json.loads(captured["request"].data.decode("utf-8"))
    assert body["model"] == "test-model"
    assert body["temperature"] == 0
    assert body["reasoning_effort"] == "low"
    assert body["max_completion_tokens"] == 256
    assert body["stream"] is False
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    instruction = body["messages"][0]["content"]
    assert "target_id MUST be exactly one of the id values listed in" in instruction
    assert "Do not create, transform, or infer an id from paths" in instruction


def test_groq_responder_builds_repair_schema_without_command_authority():
    captured = {}

    def opener(req, timeout):
        captured["request"] = req
        return _Response(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "description": "Fix the broken predicate",
                                    "patch": "--- a/nova_core/value.py\n+++ b/nova_core/value.py\n@@ -1 +1 @@\n-VALUE = 1\n+VALUE = 2\n",
                                    "paths": ["nova_core/value.py"],
                                }
                            )
                        }
                    }
                ]
            }
        )

    responder = GroqResponder(api_key="test-key", model="test-model", opener=opener, task="repair")
    result = responder('{"failure_category":"runtime_failure"}')

    assert result["paths"] == ["nova_core/value.py"]
    body = json.loads(captured["request"].data.decode("utf-8"))
    assert body["max_completion_tokens"] == 1024
    schema = body["response_format"]["json_schema"]
    assert schema["name"] == "nova_repair_proposal"
    assert schema["strict"] is True
    instruction = body["messages"][0]["content"]
    assert "no authority to execute commands" in instruction
    assert "validation commands" in instruction
    assert "minimal unified diff" in instruction


def test_groq_responder_retries_repair_diff_missing_terminal_newline():
    calls = 0
    responses = [
        {
            "description": "Fix the broken predicate",
            "patch": "--- a/nova_core/value.py\n+++ b/nova_core/value.py\n@@ -1 +1 @@\n-VALUE = 1\n+VALUE = 2",
            "paths": ["nova_core/value.py"],
        },
        {
            "description": "Fix the broken predicate",
            "patch": "--- a/nova_core/value.py\n+++ b/nova_core/value.py\n@@ -1 +1 @@\n-VALUE = 1\n+VALUE = 2\n",
            "paths": ["nova_core/value.py"],
        },
    ]

    def opener(req, timeout):
        nonlocal calls
        result = responses[calls]
        calls += 1
        return _Response({"choices": [{"message": {"content": json.dumps(result)}}]})

    responder = GroqResponder(api_key="test-key", opener=opener, task="repair")
    result = responder('{"failure_category":"step_budget"}')

    assert calls == 2
    assert result["patch"].endswith("\n")


def test_groq_responder_rejects_unknown_task():
    with pytest.raises(ValueError, match="task must be"):
        GroqResponder(api_key="test-key", task="planning")


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
