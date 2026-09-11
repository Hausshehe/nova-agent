from __future__ import annotations

import pytest

from agent.fallback_responder import FallbackResponder


def test_fallback_moves_to_next_provider_on_rate_limit() -> None:
    calls: list[str] = []
    sleeps: list[float] = []

    def groq(prompt: str):
        calls.append("groq")
        raise RuntimeError("HTTP 429")

    def openrouter(prompt: str):
        calls.append("openrouter")
        return {"action_type": "wait", "target_id": None, "value": None, "reason": "ok"}

    responder = FallbackResponder(
        [("groq", groq), ("openrouter", openrouter)],
        sleeper=sleeps.append,
    )

    assert responder("context")["action_type"] == "wait"
    assert calls == ["groq", "openrouter"]
    assert sleeps == []


def test_fallback_does_not_retry_permanent_failed_provider() -> None:
    calls: list[str] = []

    def failing(prompt: str):
        calls.append("provider")
        raise RuntimeError("HTTP 402")

    responder = FallbackResponder([("provider", failing)])

    with pytest.raises(RuntimeError, match="all reasoning providers failed"):
        responder("context")

    assert calls == ["provider"]


def test_fallback_reports_all_provider_failures() -> None:
    sleeps: list[float] = []

    def first(prompt: str):
        raise RuntimeError("429")

    def second(prompt: str):
        raise RuntimeError("timeout")

    responder = FallbackResponder(
        [("groq", first), ("gemini", second)],
        sleeper=sleeps.append,
    )

    with pytest.raises(RuntimeError) as exc:
        responder("context")

    message = str(exc.value)
    assert "groq: 429" in message
    assert "gemini: timeout" in message
    assert sleeps == [1.25]
