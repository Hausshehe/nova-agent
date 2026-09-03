from __future__ import annotations

from agent.android_bridge import AndroidBridge
from agent.core import Action, ActionType, ExecutionResult, Target, UIElement, WorldState
from agent.deterministic_reasoner import DeterministicReasoner
from agent.reasoning_context import build_reasoning_context
from agent.reasoning_response import decision_from_response


def _state(*elements: UIElement) -> WorldState:
    return WorldState(package="com.hausshehe.nova", activity="MainActivity", elements=tuple(elements), observation_id="1")


def test_reasoning_context_exposes_scrollable_container() -> None:
    state = _state(UIElement("scroll", scrollable=True, visible=True))
    context = build_reasoning_context("finish task", state, [])
    scrolls = [c for c in context.candidates if c.action_type is ActionType.SCROLL]
    assert len(scrolls) == 1
    assert scrolls[0].target == Target("scroll", "", "")
    assert scrolls[0].scrollable is True


def test_response_validates_scroll_target() -> None:
    state = _state(UIElement("scroll", scrollable=True, visible=True))
    context = build_reasoning_context("finish task", state, [])
    decision = decision_from_response(
        {"action_type": "scroll", "target": {"element_id": "scroll"}, "reason": "reveal more content"},
        context,
    )
    assert decision.action.type is ActionType.SCROLL
    assert decision.action.target == Target("scroll", "", "")


def test_deterministic_reasoner_scrolls_for_hidden_matching_goal() -> None:
    state = _state(
        UIElement("finish", text="Finish Task", clickable=True, enabled=True, visible=False),
        UIElement("scroll", scrollable=True, visible=True),
        UIElement("other", text="Other", clickable=True, enabled=True, visible=True),
    )
    context = build_reasoning_context("Finish Task", state, [])
    decision = DeterministicReasoner().decide(context)
    assert decision.action.type is ActionType.SCROLL
    assert decision.action.target == Target("scroll", "", "")


def test_android_bridge_sends_scroll_command() -> None:
    bridge = AndroidBridge()
    bridge._request = lambda payload: {"ok": True, "accepted": True, "changed": True}  # type: ignore[method-assign]
    result = bridge.execute(Action(ActionType.SCROLL, Target("scroll")))
    assert result == ExecutionResult(True, True, False, None)
