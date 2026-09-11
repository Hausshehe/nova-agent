from agent.provider_pool import ReasoningProviderPool


def test_rate_limited_provider_is_skipped_when_another_provider_is_available():
    calls = []

    def groq(prompt):
        calls.append("groq")
        raise RuntimeError("Groq request failed with HTTP 429")

    def gemini(prompt):
        calls.append("gemini")
        return {"action_type": "tap"}

    pool = ReasoningProviderPool([("groq", groq), ("gemini", gemini)])

    assert pool("prompt") == {"action_type": "tap"}
    assert calls == ["groq", "gemini"]
    assert pool.health()["groq"]["cooldown_seconds"] > 0


def test_success_rotates_starting_provider_to_spread_load():
    calls = []

    def first(prompt):
        calls.append("first")
        return {"provider": "first"}

    def second(prompt):
        calls.append("second")
        return {"provider": "second"}

    pool = ReasoningProviderPool([("first", first), ("second", second)])

    assert pool("one") == {"provider": "first"}
    assert pool("two") == {"provider": "second"}
    assert calls == ["first", "second"]


def test_retry_after_marker_controls_rate_limit_cooldown():
    now = [100.0]

    def first(prompt):
        raise RuntimeError("HTTP 429 retry-after: 6.5")

    def second(prompt):
        return {"provider": "second"}

    pool = ReasoningProviderPool([("first", first), ("second", second)], clock=lambda: now[0])
    assert pool("prompt") == {"provider": "second"}
    assert 6.4 < pool.health()["first"]["cooldown_seconds"] <= 6.5


def test_single_provider_429_retry_waits_for_retry_after():
    calls = []
    sleeps = []

    def groq(prompt):
        calls.append("groq")
        if len(calls) == 1:
            raise RuntimeError("HTTP 429 retry-after: 4.25")
        return {"action_type": "tap"}

    pool = ReasoningProviderPool([("groq", groq)], sleeper=sleeps.append)

    assert pool("prompt") == {"action_type": "tap"}
    assert calls == ["groq", "groq"]
    assert sleeps == [4.25]
    assert pool.health()["groq"]["failures"] == 0
    assert pool.health()["groq"]["successes"] == 1
