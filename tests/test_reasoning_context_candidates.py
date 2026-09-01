from agent.core import ActionType, UIElement, WorldState
from agent.reasoning_context import build_reasoning_context


def test_reasoning_context_exposes_clickable_action_candidates():
    clickable = UIElement(
        "n1",
        text="Wi-Fi",
        content_description="Network settings",
        clickable=True,
        enabled=True,
        class_name="android.widget.Button",
        bounds="[0,10][100,60]",
        checkable=True,
        checked=False,
        focused=True,
    )
    disabled = UIElement("n2", text="Disabled", clickable=True, enabled=False)
    not_clickable = UIElement("n3", text="Label", clickable=False)
    state = WorldState(package="nova", elements=(clickable, disabled, not_clickable))

    context = build_reasoning_context("Turn on Wi-Fi", state, ())

    assert len(context.candidates) == 2
    candidate = context.candidates[0]
    assert candidate.action_type is ActionType.CLICK
    assert candidate.target is not None
    assert candidate.target.element_id == "n1"
    assert candidate.target.text == "Wi-Fi"
    assert candidate.target.content_description == "Network settings"
    assert candidate.enabled is True
    assert candidate.visible is True
    assert candidate.class_name == "android.widget.Button"
    assert candidate.bounds == "[0,10][100,60]"
    assert candidate.checkable is True
    assert candidate.checked is False
    assert candidate.focused is True
    assert context.candidates[1].target.element_id == "n2"
    assert context.candidates[1].enabled is False


def test_reasoning_context_preserves_history_and_candidate_order():
    first = UIElement("n1", text="First", clickable=True)
    second = UIElement("n2", text="Second", clickable=True)
    state = WorldState(elements=(first, second))
    history = ({"step": 1, "target_id": "n1"},)

    context = build_reasoning_context("Complete task", state, history)

    assert context.history == history
    assert [candidate.target.element_id for candidate in context.candidates] == ["n1", "n2"]
