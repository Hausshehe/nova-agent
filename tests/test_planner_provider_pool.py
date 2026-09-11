import json

from agent.provider_pool import ReasoningProviderPool
from nova_core.llm_planner import LLMPlanner


def test_planner_pool_fails_over_between_independent_providers():
    calls = []

    def groq(prompt):
        calls.append("groq")
        raise RuntimeError("Groq request failed with HTTP 429")

    def openrouter(prompt):
        calls.append("openrouter")
        return {"steps": ["Click MULTI-STEP TEST", "Click CONTINUE MULTI-STEP"]}

    pool = ReasoningProviderPool([("groq", groq), ("openrouter", openrouter)])
    planner = LLMPlanner(lambda prompt: json.dumps(pool(prompt)), max_steps=3)

    assert planner.plan.__name__ == "plan"
    assert calls == []


def test_planner_transport_uses_next_provider_after_rate_limit():
    calls = []

    def first(prompt):
        calls.append("first")
        raise RuntimeError("HTTP 429 retry-after: 5")

    def second(prompt):
        calls.append("second")
        return {"steps": ["Advance the current goal"]}

    pool = ReasoningProviderPool([("first", first), ("second", second)])
    response = pool("planning prompt")

    assert response == {"steps": ["Advance the current goal"]}
    assert calls == ["first", "second"]
    assert pool.health()["first"]["cooldown_seconds"] >= 5
