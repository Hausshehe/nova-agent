import pytest

from nova_core.models import ActionType, Goal, Observation, UiElement
from nova_core.reasoning import ReasoningContext
from nova_core.reasoning_adapter import LegacyReasoningAdapter


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
