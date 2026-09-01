from agent.core import ActionType, Target, UIElement, WorldState
from agent.deterministic_reasoner import DeterministicReasoner
from agent.reasoning_context import ActionCandidate, ReasoningContext


def test_deterministic_reasoner_uses_context_candidates_not_raw_state():
    raw_only = UIElement("n1", text="Wi-Fi", clickable=True)
    selected = UIElement("n2", text="Open Settings", clickable=True)
    state = WorldState(elements=(raw_only, selected))

    context = ReasoningContext(
        goal="Open Settings",
        state=state,
        candidates=(
            ActionCandidate(
                action_type=ActionType.CLICK,
                target=Target("n2", "Open Settings", ""),
            ),
        ),
    )

    decision = DeterministicReasoner().plan(context)

    assert decision.action.type is ActionType.CLICK
    assert decision.action.target is not None
    assert decision.action.target.element_id == "n2"


def test_deterministic_reasoner_ignores_disabled_or_invisible_candidates():
    context = ReasoningContext(
        goal="Open Settings",
        state=WorldState(),
        candidates=(
            ActionCandidate(
                action_type=ActionType.CLICK,
                target=Target("n1", "Open Settings", ""),
                enabled=False,
            ),
            ActionCandidate(
                action_type=ActionType.CLICK,
                target=Target("n2", "Open Settings", ""),
                visible=False,
            ),
        ),
    )

    try:
        DeterministicReasoner().plan(context)
    except RuntimeError as exc:
        assert str(exc) == "no clickable target available"
    else:
        raise AssertionError("planner selected an unusable candidate")


def test_deterministic_reasoner_selects_back_only_when_goal_requests_it():
    context = ReasoningContext(
        goal="Go back",
        state=WorldState(),
        candidates=(
            ActionCandidate(action_type=ActionType.BACK),
            ActionCandidate(action_type=ActionType.WAIT),
        ),
    )

    decision = DeterministicReasoner().plan(context)

    assert decision.action.type is ActionType.BACK
    assert decision.action.target is None


def test_deterministic_reasoner_selects_wait_only_when_goal_requests_it():
    context = ReasoningContext(
        goal="Wait",
        state=WorldState(),
        candidates=(
            ActionCandidate(action_type=ActionType.BACK),
            ActionCandidate(action_type=ActionType.WAIT),
        ),
    )

    decision = DeterministicReasoner().plan(context)

    assert decision.action.type is ActionType.WAIT
    assert decision.action.target is None


def test_deterministic_reasoner_does_not_use_global_actions_as_click_fallback():
    context = ReasoningContext(
        goal="Open Settings",
        state=WorldState(),
        candidates=(
            ActionCandidate(action_type=ActionType.BACK),
            ActionCandidate(action_type=ActionType.WAIT),
        ),
    )

    try:
        DeterministicReasoner().plan(context)
    except RuntimeError as exc:
        assert str(exc) == "no clickable target available"
    else:
        raise AssertionError("planner used a global action without an explicit goal")
