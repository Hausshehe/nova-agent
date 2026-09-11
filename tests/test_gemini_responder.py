import json

import pytest

from agent.gemini_responder import DEFAULT_MODEL, DEFAULT_TIMEOUT_SECONDS, GeminiResponder


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


def _payload(result):
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(result)}]}}]}


def test_gemini_responder_defaults_to_current_agent_model_and_timeout():
    captured = {}

    def opener(req, timeout):
        captured["request"] = req
        captured["timeout"] = timeout
        return _Response(_payload({"action_type": "tap", "target_id": "target", "value": None, "reason": "advance"}))

    result = GeminiResponder(api_key="test-key", opener=opener)("Tap target")

    assert result["target_id"] == "target"
    assert captured["timeout"] == DEFAULT_TIMEOUT_SECONDS == 60.0
    assert DEFAULT_MODEL == "gemini-3.6-flash"
    assert "/models/gemini-3.6-flash:generateContent" in captured["request"].full_url
    body = json.loads(captured["request"].data.decode("utf-8"))
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["responseSchema"]["required"] == [
        "action_type", "target_id", "value", "reason"
    ]


def test_gemini_responder_supports_planning_task():
    captured = {}

    def opener(req, timeout):
        captured["request"] = req
        return _Response(_payload({"steps": ["Click MULTI-STEP TEST", "Click CONTINUE MULTI-STEP"]}))

    result = GeminiResponder(api_key="test-key", model="gemini-3.6-flash", task="planning", opener=opener)("Finish Multi-Step Test")

    assert result["steps"] == ["Click MULTI-STEP TEST", "Click CONTINUE MULTI-STEP"]
    body = json.loads(captured["request"].data.decode("utf-8"))
    assert "mission planning engine" in body["system_instruction"]["parts"][0]["text"]
    assert body["generationConfig"]["responseSchema"]["required"] == ["steps"]


def test_gemini_responder_requires_api_key():
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY is not set"):
        GeminiResponder(api_key="")("{}")


def test_gemini_responder_rejects_blank_prompt():
    with pytest.raises(ValueError, match="prompt must not be blank"):
        GeminiResponder(api_key="test-key")("   ")


def test_gemini_responder_does_not_retry_timeout():
    calls = 0

    def opener(req, timeout):
        nonlocal calls
        calls += 1
        raise TimeoutError()

    with pytest.raises(RuntimeError, match="timed out"):
        GeminiResponder(api_key="test-key", opener=opener)("{}")

    assert calls == 1


def test_gemini_responder_normalizes_connection_aborted_for_provider_pool():
    def opener(req, timeout):
        raise ConnectionAbortedError(103, "Software caused connection abort")

    with pytest.raises(RuntimeError, match="Gemini request connection failed: \[Errno 103\] Software caused connection abort"):
        GeminiResponder(api_key="test-key", opener=opener)("{}")
