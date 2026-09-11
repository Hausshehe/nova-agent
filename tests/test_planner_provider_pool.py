from agent.provider_pool import ReasoningProviderPool


def test_planner_pool_fails_over_between_independent_providers():
    calls = []

    def groq(prompt):
        calls.append("groq")
        raise RuntimeError("Groq request failed with HTTP 429")

    def openrouter(prompt):
        calls.append("openrouter")
        return {"steps": ["Click MULTI-STEP TEST"]}

    pool = ReasoningProviderPool([("groq", groq), ("openrouter", openrouter)])

    assert pool("planning prompt") == {"steps": ["Click MULTI-STEP TEST"]}
    assert calls == ["groq", "openrouter"]
    assert pool.health()["groq"]["cooldown_seconds"] > 0


def test_planner_pool_uses_third_provider_after_two_rate_limits():
    calls = []

    def first(prompt):
        calls.append("first")
        raise RuntimeError("HTTP 429")

    def second(prompt):
        calls.append("second")
        raise RuntimeError("HTTP 429")

    def third(prompt):
        calls.append("third")
        return {"steps": ["Finish the current goal"]}

    pool = ReasoningProviderPool([("first", first), ("second", second), ("third", third)])

    assert pool("planning prompt") == {"steps": ["Finish the current goal"]}
    assert calls == ["first", "second", "third"]


def test_planner_pool_reports_bounded_failure_when_every_provider_fails():
    calls = []

    def fail(name):
        def responder(prompt):
            calls.append(name)
            raise RuntimeError(f"{name} HTTP 429")
        return responder

    pool = ReasoningProviderPool([("groq", fail("groq")), ("gemini", fail("gemini")), ("cerebras", fail("cerebras"))])

    try:
        pool("planning prompt")
    except RuntimeError as exc:
        assert str(exc).startswith("all reasoning providers failed:")
    else:
        raise AssertionError("expected bounded provider-pool failure")
    assert calls == ["groq", "gemini", "cerebras"]
