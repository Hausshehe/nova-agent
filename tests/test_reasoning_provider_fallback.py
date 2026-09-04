import pytest

from agent.fallback_responder import FallbackResponder


def test_fallback_uses_next_provider_after_failure():
    calls = []

    def groq(prompt):
        calls.append("groq")
        raise RuntimeError("HTTP 429")

    def backup(prompt):
        calls.append("backup")
        return {"action_type": "tap", "target_id": "target", "value": None, "reason": "backup"}

    result = FallbackResponder([("groq", groq), ("backup", backup)])("context")

    assert result["target_id"] == "target"
    assert calls == ["groq", "backup"]


def test_fallback_is_bounded_and_reports_all_failures():
    calls = []

    def fail(name):
        def responder(prompt):
            calls.append(name)
            raise RuntimeError(f"{name} failed")

        return responder

    with pytest.raises(RuntimeError, match="all reasoning providers failed") as exc_info:
        FallbackResponder([("groq", fail("groq")), ("gemini", fail("gemini"))])("context")

    assert calls == ["groq", "gemini"]
    assert "groq: groq failed" in str(exc_info.value)
    assert "gemini: gemini failed" in str(exc_info.value)


def test_fallback_requires_at_least_one_provider():
    with pytest.raises(ValueError, match="at least one reasoning responder"):
        FallbackResponder([])
