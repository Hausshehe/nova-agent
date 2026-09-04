from nova_core.action_verifier import ActionExecutionVerifier
from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation


def _observations():
    before = Observation("pkg", "MainActivity", (), 1)
    after = Observation("pkg", "MainActivity", (), 2)
    decision = Decision(Action(ActionType.TAP, target_id="target"))
    return before, after, decision


def test_action_execution_verifier_accepts_explicit_action_goal_after_changed_execution():
    before, after, decision = _observations()
    assert ActionExecutionVerifier().verify(
        Goal("Tap Test Navigation Action"),
        before,
        decision,
        ExecutionResult(accepted=True, changed=True),
        after,
    )


def test_action_execution_verifier_rejects_unchanged_execution():
    before, after, decision = _observations()
    assert not ActionExecutionVerifier().verify(
        Goal("Tap Test Navigation Action"),
        before,
        decision,
        ExecutionResult(accepted=True, changed=False),
        after,
    )


def test_action_execution_verifier_rejects_non_action_goal():
    before, after, decision = _observations()
    assert not ActionExecutionVerifier().verify(
        Goal("Navigation Completed"),
        before,
        decision,
        ExecutionResult(accepted=True, changed=True),
        after,
    )


def test_action_execution_verifier_requires_a_fresh_changed_observation():
    before, _, decision = _observations()
    assert not ActionExecutionVerifier().verify(
        Goal("Tap Test Navigation Action"),
        before,
        decision,
        ExecutionResult(accepted=True, changed=True),
        before,
    )
