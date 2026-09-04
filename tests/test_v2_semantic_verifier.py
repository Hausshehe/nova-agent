from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, UiElement
from nova_core.semantic_verifier import SemanticGoalVerifier


def _observation(*elements, activity="Main"):
    return Observation(
        package="com.example.app",
        activity=activity,
        elements=tuple(elements),
    )


def _tap_result():
    return ExecutionResult(accepted=True, changed=True)


def _decision():
    return Decision(Action(type=ActionType.TAP, target_id="target"))


def test_open_goal_requires_new_visible_target_or_activity_change():
    verifier = SemanticGoalVerifier()
    before = _observation(UiElement(id="other", text="Home"))
    after = _observation(UiElement(id="target", text="Settings", clickable=True))
    assert verifier.verify(Goal("Open Settings"), before, _decision(), _tap_result(), after)


def test_open_goal_is_proven_by_activity_change_even_when_label_preexists():
    verifier = SemanticGoalVerifier()
    before = _observation(UiElement(id="target", text="Settings"), activity="Home")
    after = _observation(UiElement(id="target", text="Settings"), activity="Settings")
    assert verifier.verify(Goal("Open Settings"), before, _decision(), _tap_result(), after)


def test_open_goal_rejects_unchanged_target_on_same_activity():
    verifier = SemanticGoalVerifier()
    before = _observation(UiElement(id="target", text="Settings"))
    after = _observation(UiElement(id="target", text="Settings"))
    assert not verifier.verify(Goal("Open Settings"), before, _decision(), _tap_result(), after)


def test_enable_goal_requires_checkable_checked_state():
    verifier = SemanticGoalVerifier()
    before = _observation(UiElement(id="wifi", text="Wi-Fi", checkable=True, checked=False))
    after = _observation(UiElement(id="wifi", text="Wi-Fi", checkable=True, checked=True))
    assert verifier.verify(Goal("Enable Wi-Fi"), before, _decision(), _tap_result(), after)


def test_enable_goal_rejects_visible_but_unchecked_target():
    verifier = SemanticGoalVerifier()
    before = _observation(UiElement(id="wifi", text="Wi-Fi", checkable=True, checked=False))
    after = _observation(UiElement(id="wifi", text="Wi-Fi", checkable=True, checked=False))
    assert not verifier.verify(Goal("Enable Wi-Fi"), before, _decision(), _tap_result(), after)


def test_disable_goal_requires_unchecked_state():
    verifier = SemanticGoalVerifier()
    before = _observation(UiElement(id="wifi", text="Wi-Fi", checkable=True, checked=True))
    after = _observation(UiElement(id="wifi", text="Wi-Fi", checkable=True, checked=False))
    assert verifier.verify(Goal("Disable Wi-Fi"), before, _decision(), _tap_result(), after)


def test_completion_goal_requires_target_and_completion_marker():
    verifier = SemanticGoalVerifier()
    before = _observation(UiElement(id="status", text="Step 2 started"))
    after = _observation(UiElement(id="status", text="Multi-Step Test completed"))
    assert verifier.verify(
        Goal("Finish Multi-Step Test"), before, _decision(), _tap_result(), after
    )


def test_completion_goal_matches_target_without_repeating_completion_verb():
    verifier = SemanticGoalVerifier()
    before = _observation(UiElement(id="status", text="Recovery ready"))
    after = _observation(UiElement(id="status", text="Recovery completed"))
    assert verifier.verify(
        Goal("Recovery Completed"), before, _decision(), _tap_result(), after
    )


def test_completion_goal_does_not_accept_still_visible_finish_button():
    verifier = SemanticGoalVerifier()
    before = _observation(UiElement(id="finish", text="Finish Multi-Step", clickable=True))
    after = _observation(UiElement(id="finish", text="Finish Multi-Step", clickable=True))
    assert not verifier.verify(
        Goal("Finish Multi-Step Test"), before, _decision(), _tap_result(), after
    )


def test_completion_goal_rejects_intermediate_multi_step_state():
    verifier = SemanticGoalVerifier()
    before = _observation(UiElement(id="status", text="Multi-Step ready"))
    after = _observation(UiElement(id="status", text="Step 2 started"))
    assert not verifier.verify(
        Goal("Finish Multi-Step Test"), before, _decision(), _tap_result(), after
    )


def test_unknown_goal_semantics_fail_closed():
    verifier = SemanticGoalVerifier()
    before = _observation(UiElement(id="target", text="Account"))
    after = _observation(UiElement(id="target", text="Account Updated"))
    assert not verifier.verify(
        Goal("Make my account perfect"), before, _decision(), _tap_result(), after
    )


def test_action_goal_keeps_existing_action_semantics():
    verifier = SemanticGoalVerifier()
    before = _observation(UiElement(id="target", text="Test Navigation Action"))
    after = _observation(UiElement(id="target", text="Recovery Completed"))
    assert verifier.verify(
        Goal("Tap Test Navigation Action"), before, _decision(), _tap_result(), after
    )
