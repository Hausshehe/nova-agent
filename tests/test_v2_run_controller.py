import pytest

from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, UiElement, RunStatus
from nova_core.run_controller import RunController
from nova_core.state_machine import InvalidTransition, RunState


def observation(revision: int = 1) -> Observation:
    return Observation(package="com.example", activity="MainActivity", revision=revision)


def decision() -> Decision:
    return Decision(action=Action(type=ActionType.TAP, target_id="button"))


def test_controller_happy_path_is_explicit_and_bounded():
    controller = RunController(Goal("tap the button"), max_steps=1)

    assert controller.move(RunState.OBSERVING) is RunState.OBSERVING
    controller.record_observation(observation())
    controller.move(RunState.DECIDING)
    controller.record_decision(decision())
    controller.move(RunState.EXECUTING)
    controller.record_execution(ExecutionResult(accepted=True, changed=True))
    controller.move(RunState.VERIFYING)

    result = controller.finish(RunStatus.SUCCEEDED)

    assert result.status is RunStatus.SUCCEEDED
    assert result.steps == 1
    assert controller.result() == result


def test_controller_can_reobserve_after_verification_failure():
    controller = RunController(Goal("finish"), max_steps=2)
    controller.move(RunState.OBSERVING)
    controller.record_observation(observation())
    controller.move(RunState.DECIDING)
    controller.record_decision(decision())
    controller.move(RunState.EXECUTING)
    controller.record_execution(ExecutionResult(accepted=False, changed=False, error="rejected"))
    controller.move(RunState.VERIFYING)
    controller.move(RunState.OBSERVING)
    controller.record_observation(observation(revision=2))

    assert controller.state is RunState.OBSERVING
    assert controller.steps == 0
    assert controller.observation.revision == 2


def test_controller_rejects_recording_data_in_wrong_state():
    controller = RunController(Goal("finish"))

    with pytest.raises(InvalidTransition):
        controller.record_observation(observation())
    with pytest.raises(InvalidTransition):
        controller.record_decision(decision())
    with pytest.raises(InvalidTransition):
        controller.record_execution(ExecutionResult(accepted=True, changed=True))


def test_controller_rejects_non_terminal_finish_status():
    controller = RunController(Goal("finish"))

    with pytest.raises(ValueError):
        controller.finish(RunStatus.RUNNING)


def test_controller_enforces_step_budget():
    controller = RunController(Goal("finish"), max_steps=1)
    controller.move(RunState.OBSERVING)
    controller.move(RunState.DECIDING)
    controller.record_decision(decision())
    controller.move(RunState.EXECUTING)
    controller.record_execution(ExecutionResult(accepted=True, changed=True))

    with pytest.raises(RuntimeError, match="step budget exhausted"):
        controller.record_execution(ExecutionResult(accepted=True, changed=True))


def test_controller_result_is_unavailable_before_terminal_state():
    controller = RunController(Goal("finish"))
    assert controller.result() is None


def test_controller_aborts_explicitly():
    controller = RunController(Goal("finish"))
    controller.move(RunState.ABORTED)

    result = controller.result()

    assert result is not None
    assert result.status is RunStatus.ABORTED
    assert result.steps == 0
