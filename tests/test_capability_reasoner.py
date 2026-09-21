from agent.capability_router import Capability, CapabilityRouter, pool
from nova_core.capability_reasoner import CapabilityRoutedReasoner
from nova_core.models import ActionType, Goal, Observation, UiElement
from nova_core.reasoning import ReasoningContext


def test_capability_routed_reasoner_uses_action_selection_pool():
    calls = []

    def action_provider(prompt):
        calls.append(prompt)
        return {
            "action_type": "tap",
            "target_id": "button",
            "reason": "advance the current intent",
        }

    def wrong_provider(prompt):
        raise AssertionError("wrong capability pool was selected")

    router = CapabilityRouter({
        Capability.ACTION_SELECTION: pool([("groq", action_provider)]),
        Capability.REASONING: pool([("cerebras", wrong_provider)]),
    })

    context = ReasoningContext(
        goal=Goal("Tap Continue"),
        observation=Observation(
            package="com.example.app",
            activity="MainActivity",
            revision=1,
            elements=(UiElement(id="button", text="Continue", clickable=True),),
        ),
        history=(),
    )

    decision = CapabilityRoutedReasoner(router).decide(context)

    assert decision.action.type is ActionType.TAP
    assert decision.action.target_id == "button"
    assert len(calls) == 1


def test_capability_routed_reasoner_keeps_capability_health_independent():
    calls = {"reasoning": 0, "action": 0}

    def reasoning(prompt):
        calls["reasoning"] += 1
        raise RuntimeError("HTTP 429 rate limit")

    def action(prompt):
        calls["action"] += 1
        return {
            "action_type": "tap",
            "target_id": "button",
            "reason": "still available",
        }

    router = CapabilityRouter({
        Capability.REASONING: pool(
            [("groq", reasoning)],
            transient_retries=0,
            rate_limit_cooldown_seconds=30,
        ),
        Capability.ACTION_SELECTION: pool([("groq", action)]),
    })

    try:
        router(Capability.REASONING, "reason")
    except RuntimeError:
        pass

    context = ReasoningContext(
        goal=Goal("Tap Continue"),
        observation=Observation(
            package="com.example.app",
            activity="MainActivity",
            revision=1,
            elements=(UiElement(id="button", text="Continue", clickable=True),),
        ),
        history=(),
    )

    decision = CapabilityRoutedReasoner(router).decide(context)

    assert decision.action.target_id == "button"
    assert calls == {"reasoning": 1, "action": 1}
