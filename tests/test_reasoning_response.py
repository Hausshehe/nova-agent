import pytest

from agent.core import ActionType, UIElement, WorldState
from agent.reasoning_context import build_reasoning_context
from agent.reasoning_response import InvalidReasoningResponse, decision_from_response


def context(*elements):
    state = WorldState(package="nova", elements=tuple(elements))
    return build_reasoning_context("Tap Continue", state, [])


def test_valid_click_response_becomes_decision():
    button = UIElement("n1", text="Continue", clickable=True)
    decision = decision_from_response(
        {
            "action_type": ActionType.CLICK.value,
            "target": {"element_id": "n1"},
            "reason": "matches the goal",
        },
        context(button),
    )

    assert decision.action.type is ActionType.CLICK
    assert decision.action.target.element_id == "n1"
    assert decision.rationale == "matches the goal"


def test_click_response_rejects_unknown_target():
    with pytest.raises(InvalidReasoningResponse, match="not available"):
        decision_from_response(
            {
                "action_type": ActionType.CLICK.value,
                "target": {"element_id": "stale"},
            },
            context(UIElement("n1", text="Continue", clickable=True)),
        )


def test_click_response_rejects_disabled_target():
    with pytest.raises(InvalidReasoningResponse, match="enabled and visible"):
        decision_from_response(
            {
                "action_type": ActionType.CLICK.value,
                "target": {"element_id": "n1"},
            },
            context(UIElement("n1", text="Continue", clickable=True, enabled=False)),
        )


def test_back_and_wait_are_valid_without_targets():
    ctx = context(UIElement("n1", text="Continue", clickable=True))

    back = decision_from_response({"action_type": ActionType.BACK.value}, ctx)
    wait = decision_from_response({"action_type": ActionType.WAIT.value}, ctx)

    assert back.action.type is ActionType.BACK
    assert wait.action.type is ActionType.WAIT


def test_back_rejects_target():
    with pytest.raises(InvalidReasoningResponse, match="target is not allowed"):
        decision_from_response(
            {
                "action_type": ActionType.BACK.value,
                "target": {"element_id": "n1"},
            },
            context(UIElement("n1", text="Continue", clickable=True)),
        )


def test_click_requires_target_object():
    with pytest.raises(InvalidReasoningResponse, match="requires a target object"):
        decision_from_response(
            {"action_type": ActionType.CLICK.value},
            context(UIElement("n1", text="Continue", clickable=True)),
        )


def test_invalid_action_type_is_rejected():
    with pytest.raises(InvalidReasoningResponse, match="invalid action_type"):
        decision_from_response(
            {"action_type": "launch_missiles"},
            context(UIElement("n1", text="Continue", clickable=True)),
        )
