from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, UiElement, RunStatus
from nova_core.runtime_brain import RuntimeBrain
from nova_core.state_machine import RunState


def _observation(revision: int) -> Observation:
    return Observation(
        package="com.example.app",
        activity="MainActivity",
        revision=revision,
        elements=(UiElement(id="button", text="Continue", clickable=True),),
    )


def _decision() -> Decision:
    return Decision(Action(type=ActionType.TAP, target_id="button"), reason="continue")


def test_runtime_brain_owns_observe_decide_execute_verify_loop():
    brain = RuntimeBrain.create(Goal("Finish the task"), max_steps=3)

    brain.start()
    assert brain.state is RunState.OBSERVING

    first = _observation(1)
    brain.record_observation(first)
    assert brain.state is RunState.DECIDING
    assert brain.reasoning_context().observation == first

    brain.record_decision(_decision())
    assert brain.state is RunState.EXECUTING

    brain.record_execution(ExecutionResult(accepted=True, changed=True))
    assert brain.state is RunState.VERIFYING

    second = _observation(2)
    brain.record_post_observation(second)
    assert brain.state is RunState.OBSERVING
    assert brain.controller.history[-1].post_observation == second


def test_runtime_brain_success_is_decided_during_post_observation_verification():
    brain = RuntimeBrain.create(Goal("Finish the task"))
    brain.start()
    brain.record_observation(_observation(1))
    brain.record_decision(_decision())
    brain.record_execution(ExecutionResult(accepted=True, changed=True))

    result = brain.verify_post_observation(_observation(2), goal_achieved=True)

    assert result is not None
    assert result.status is RunStatus.SUCCEEDED
    assert result.steps == 1
    assert brain.goal_verified is True
    assert brain.state is RunState.SUCCEEDED
    assert brain.controller.history[-1].post_observation == _observation(2)


def test_runtime_brain_completion_requires_verification_state():
    brain = RuntimeBrain.create(Goal("Finish the task"))
    brain.start()

    try:
        brain.complete()
    except RuntimeError as exc:
        assert "verifying state" in str(exc)
    else:
        raise AssertionError("complete() must not bypass verification")


def test_runtime_brain_completion_requires_fresh_post_observation():
    brain = RuntimeBrain.create(Goal("Finish the task"))
    brain.start()
    brain.record_observation(_observation(1))
    brain.record_decision(_decision())
    brain.record_execution(ExecutionResult(accepted=True, changed=True))

    try:
        brain.complete()
    except RuntimeError as exc:
        assert "post-observation" in str(exc)
    else:
        raise AssertionError("complete() must not bypass post-observation verification")

    assert brain.state is RunState.VERIFYING
    assert brain.goal_verified is False


def test_runtime_brain_failure_does_not_claim_goal_completion():
    brain = RuntimeBrain.create(Goal("Finish the task"))
    brain.start()

    result = brain.fail("reasoning provider unavailable")

    assert result.status is RunStatus.FAILED
    assert result.error == "reasoning provider unavailable"
    assert brain.goal_verified is False
    assert brain.state is RunState.FAILED
