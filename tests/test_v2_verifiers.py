from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, UiElement
from nova_core.verifiers import VisibleTextVerifier


def obs(*elements):
    return Observation("com.example", "MainActivity", tuple(elements), revision=2)


def decision():
    return Decision(Action(ActionType.TAP, target_id="button"))


def test_verifier_requires_accepted_changed_execution():
    verifier = VisibleTextVerifier()
    goal = Goal("settings")

    assert not verifier.verify(goal, obs(), decision(), ExecutionResult(False, True), obs(UiElement("x", text="settings")))
    assert not verifier.verify(goal, obs(), decision(), ExecutionResult(True, False), obs(UiElement("x", text="settings")))


def test_verifier_accepts_goal_visible_in_fresh_ui():
    verifier = VisibleTextVerifier()
    goal = Goal("Open Settings")
    after = obs(UiElement("x", text="Open Settings", visible=True))

    assert verifier.verify(goal, obs(), decision(), ExecutionResult(True, True), after)


def test_verifier_uses_content_description():
    verifier = VisibleTextVerifier()
    goal = Goal("settings")
    after = obs(UiElement("x", content_description="Settings", visible=True))

    assert verifier.verify(goal, obs(), decision(), ExecutionResult(True, True), after)


def test_verifier_rejects_invisible_text_and_partial_tokens():
    verifier = VisibleTextVerifier()
    goal = Goal("open settings")

    assert not verifier.verify(
        goal,
        obs(),
        decision(),
        ExecutionResult(True, True),
        obs(UiElement("x", text="Open Settings", visible=False)),
    )
    assert not verifier.verify(
        goal,
        obs(),
        decision(),
        ExecutionResult(True, True),
        obs(UiElement("x", text="Settings", visible=True)),
    )
