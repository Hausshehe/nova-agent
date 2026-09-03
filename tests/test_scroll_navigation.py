from __future__ import annotations

from agent.core import ActionType, UIElement, WorldState
from agent.reasoning_context import build_reasoning_context
from agent.reasoning_response import decision_from_response


def test_scrollable_container_is_an_action_candidate():
    state = WorldState(
        package="test",
        activity="Main",
        elements=(
            UIElement("viewport", scrollable=True, bounds="[0,80][720,1532]"),
            UIElement("visible", "Visible", clickable=True, bounds="[32,120][688,216]"),
            UIElement("offscreen", "Offscreen", clickable=True, bounds="[32,1571][688,1667]"),
        ),
    )
    context = build_reasoning_context("Tap Offscreen", state, [])

    assert any(c.action_type is ActionType.SCROLL and c.target.element_id == "viewport" for c in context.candidates)
    assert not any(c.action_type is ActionType.CLICK and c.target.element_id == "offscreen" for c in context.candidates)
    assert any(c.action_type is ActionType.CLICK and c.target.element_id == "visible" for c in context.candidates)


def test_scroll_response_is_validated_against_scroll_candidate():
    state = WorldState(
        package="test",
        activity="Main",
        elements=(UIElement("viewport", scrollable=True, bounds="[0,80][720,1532]"),),
    )
    context = build_reasoning_context("Reveal more", state, [])
    decision = decision_from_response(
        {"action_type": "scroll", "target": {"element_id": "viewport"}, "reason": "Reveal more content"},
        context,
    )

    assert decision.action.type is ActionType.SCROLL
    assert decision.action.target.element_id == "viewport"
