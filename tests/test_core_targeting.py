from agent.core import UIElement, WorldState, Action, ActionType, ExecutionResult, TransitionVerifier
from agent.targeting import find_target


def elements():
    return (
        UIElement("n1", text="Disabled", clickable=True, enabled=False),
        UIElement("n2", text="Test Navigation Action", clickable=True),
        UIElement("n3", content_description="Navigation settings", clickable=True),
        UIElement("n4", text="Static label", clickable=False),
    )


def test_targeting_prefers_exact_visible_text():
    target = find_target("Tap Test Navigation Action", elements())
    assert target is not None
    assert target.element_id == "n2"


def test_targeting_ignores_disabled_and_non_clickable_nodes():
    target = find_target("Disabled", elements())
    assert target is None


def test_targeting_can_use_content_description():
    target = find_target("Navigation settings", elements())
    assert target is not None
    assert target.element_id == "n3"


def test_verifier_rejects_accepted_but_unchanged_action():
    state = WorldState(package="nova", elements=elements())
    result = ExecutionResult(accepted=True, changed=False)
    assert TransitionVerifier().verify(state, state, result) is False


def test_verifier_accepts_real_transition():
    before = WorldState(package="nova", observation_id="1", elements=elements())
    after = WorldState(package="nova", observation_id="2", elements=elements()[:-1])
    result = ExecutionResult(accepted=True, changed=True)
    assert TransitionVerifier().verify(before, after, result) is True
