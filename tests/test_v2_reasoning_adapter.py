import json

import pytest

from nova_core.models import ActionType, Goal, Observation, UiElement
from nova_core.reasoning import ReasoningContext
from nova_core.reasoning_adapter import LLMReasoner, LegacyReasoningAdapter


class FakeProvider:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def decide(self, goal, observation, history):
        self.calls.append((goal, observation, history))
        return self.result


def context():
    return ReasoningContext(
        goal=Goal("tap the button"),
        observation=Observation(
            package="com.example",
            activity="MainActivity",
            elements=(UiElement(id="button", text="Tap", clickable=True),),
        ),
    )


def test_adapter_translates_click_and_preserves_context():
    provider = FakeProvider({
        "action_type": "click",
        "target": {"element_id": "button"},
        "reason": "target matches goal",
    })

    decision = LegacyReasoningAdapter(provider).decide(context())

    assert decision.action.type is ActionType.TAP
    assert decision.action.target_id == "button"
    assert decision.reason == "target matches goal"
    assert provider.calls[0][0] == "tap the button"


def test_adapter_translates_back():
    provider = FakeProvider({"action_type": "back"})
    decision = LegacyReasoningAdapter(provider).decide(context())
    assert decision.action.type is ActionType.BACK


def test_adapter_translates_scroll():
    provider = FakeProvider({
        "action_type": "scroll",
        "target": {"element_id": "button"},
    })
    decision = LegacyReasoningAdapter(provider).decide(context())
    assert decision.action.type is ActionType.SCROLL
    assert decision.action.target_id == "button"


@pytest.mark.parametrize(
    "result",
    [None, [], "click", {"action_type": "unknown"}],
)
def test_adapter_fails_closed_for_invalid_output(result):
    with pytest.raises(ValueError):
        LegacyReasoningAdapter(FakeProvider(result)).decide(context())


def test_adapter_rejects_click_without_target_id():
    provider = FakeProvider({"action_type": "click", "target": {}})
    with pytest.raises(ValueError, match="target.element_id"):
        LegacyReasoningAdapter(provider).decide(context())


def test_llm_reasoner_serializes_v2_context_and_validates_live_target():
    received = []

    def responder(prompt):
        received.append(prompt)
        payload = json.loads(prompt)
        assert payload["goal"] == "tap the button"
        assert payload["observation"]["revision"] == 0
        assert payload["observation"]["elements"][0]["id"] == "button"
        assert payload["observation"]["elements"][0]["clickable"] is True
        assert payload["history"] == []
        return {
            "action_type": "tap",
            "target_id": "button",
            "reason": "selected the visible button",
        }

    decision = LLMReasoner(responder).decide(context())

    assert received
    assert decision.action.type is ActionType.TAP
    assert decision.action.target_id == "button"
    assert decision.target_label == "Tap"
    assert decision.reason == "selected the visible button"


def test_llm_reasoner_rejects_stale_or_non_clickable_target():
    stale = LLMReasoner(
        lambda prompt: {
            "action_type": "tap",
            "target_id": "stale",
        }
    )
    with pytest.raises(ValueError, match="not available"):
        stale.decide(context())

    non_clickable_context = ReasoningContext(
        goal=Goal("tap the button"),
        observation=Observation(
            package="com.example",
            activity="MainActivity",
            elements=(UiElement(id="button", text="Tap", clickable=False),),
        ),
    )
    non_clickable = LLMReasoner(
        lambda prompt: {
            "action_type": "tap",
            "target_id": "button",
        }
    )
    with pytest.raises(ValueError, match="not available"):
        non_clickable.decide(non_clickable_context)


def test_llm_reasoner_wraps_responder_failure():
    def failing_responder(prompt):
        raise OSError("connection failed")

    with pytest.raises(RuntimeError, match="reasoning provider failed"):
        LLMReasoner(failing_responder).decide(context())


def test_llm_reasoner_rejects_invalid_action_shape():
    reasoner = LLMReasoner(lambda prompt: {
        "action_type": "back",
        "target_id": "button",
    })
    with pytest.raises(ValueError, match="not allowed"):
        reasoner.decide(context())
