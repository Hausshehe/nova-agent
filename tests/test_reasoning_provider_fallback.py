import pytest

from agent.fallback_responder import FallbackResponder


def test_fallback_retries_transient_failure_before_using_next_provider():
    calls = []
    sleeps = []

    def groq(prompt):
        calls.append("groq")
        raise RuntimeError("HTTP 429")

    def backup(prompt):
        calls.append("backup")
        return {"action_type": "tap", "target_id": "target", "value": None, "reason": "backup"}

    result = FallbackResponder(
        [("groq", groq), ("backup", backup)],
        sleeper=sleeps.append,
    )("context")

    assert result["target_id"] == "target"
    assert calls == ["groq", "groq", "backup"]
    assert sleeps == [1.25]


def test_fallback_is_bounded_and_reports_all_failures():
    calls = []
    sleeps = []

    def fail(name):
        def responder(prompt):
            calls.append(name)
            raise RuntimeError(f"{name} failed")

        return responder

    with pytest.raises(RuntimeError, match="all reasoning providers failed") as exc_info:
        FallbackResponder(
            [("groq", fail("groq")), ("gemini", fail("gemini"))],
            sleeper=sleeps.append,
        )("context")

    assert calls == ["groq", "gemini"]
    assert "groq: groq failed" in str(exc_info.value)
    assert "gemini: gemini failed" in str(exc_info.value)
    assert sleeps == []


def test_fallback_requires_at_least_one_provider():
    with pytest.raises(ValueError, match="at least one reasoning responder"):
        FallbackResponder([])
