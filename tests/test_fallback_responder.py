import pytest

from agent.fallback_responder import FallbackResponder


def test_transient_failure_is_retried_once_before_success():
    calls = 0
    sleeps = []

    def responder(prompt):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("provider failed with HTTP 429")
        return {"action_type": "tap"}

    result = FallbackResponder(
        [("groq", responder)],
        retry_delay_seconds=1.25,
        sleeper=sleeps.append,
    )("prompt")

    assert result == {"action_type": "tap"}
    assert calls == 2
    assert sleeps == [1.25]


def test_transient_failure_moves_to_next_provider_after_bounded_retry():
    calls = []
    sleeps = []

    def first(prompt):
        calls.append("first")
        raise RuntimeError("upstream HTTP 502 temporarily overloaded")

    def second(prompt):
        calls.append("second")
        return {"action_type": "tap"}

    result = FallbackResponder(
        [("first", first), ("second", second)],
        sleeper=sleeps.append,
    )("prompt")

    assert result == {"action_type": "tap"}
    assert calls == ["first", "first", "second"]
    assert sleeps == [1.25]


def test_permanent_failure_is_not_retried():
    calls = 0
    sleeps = []

    def responder(prompt):
        nonlocal calls
        calls += 1
        raise RuntimeError("provider request failed with HTTP 402")

    with pytest.raises(RuntimeError, match="all reasoning providers failed"):
        FallbackResponder(
            [("cerebras", responder)],
            sleeper=sleeps.append,
        )("prompt")

    assert calls == 1
    assert sleeps == []


def test_invalid_response_value_error_is_not_retried():
    calls = 0

    def responder(prompt):
        nonlocal calls
        calls += 1
        raise ValueError("invalid reasoning response")

    with pytest.raises(RuntimeError, match="all reasoning providers failed"):
        FallbackResponder([("provider", responder)], sleeper=lambda _: None)("prompt")

    assert calls == 1


def test_transient_retries_can_be_disabled():
    calls = 0

    def responder(prompt):
        nonlocal calls
        calls += 1
        raise RuntimeError("HTTP 503 unavailable")

    with pytest.raises(RuntimeError, match="all reasoning providers failed"):
        FallbackResponder(
            [("provider", responder)],
            transient_retries=0,
            sleeper=lambda _: None,
        )("prompt")

    assert calls == 1
