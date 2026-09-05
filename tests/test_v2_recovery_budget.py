from nova_core.adapters.android import AndroidBridgeAdapter
from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, RunStatus, UiElement
from nova_core.runtime import Runtime
from nova_core.run_controller import RunController
from nova_core.state_machine import RunState


def _observation(revision: int) -> Observation:
    return Observation(
        package="test.package",
        activity="test.Activity",
        elements=(UiElement(id="target", text="Target", clickable=True, enabled=True),),
        revision=revision,
    )


def test_rejected_execution_does_not_consume_action_budget():
    controller = RunController(Goal("finish"), max_steps=3)
    controller.move(RunState.OBSERVING)
    controller.record_observation(_observation(1))
    controller.move(RunState.DECIDING)
    controller.record_decision(Decision(Action(ActionType.TAP, target_id="bad")))
    controller.move(RunState.EXECUTING)
    controller.record_execution(ExecutionResult(accepted=False, changed=False, error="rejected"))
    assert controller.steps == 0
    assert len(controller.history) == 1


def test_successful_changed_actions_still_consume_action_budget():
    controller = RunController(Goal("finish"), max_steps=1)
    controller.move(RunState.OBSERVING)
    controller.record_observation(_observation(1))
    controller.move(RunState.DECIDING)
    controller.record_decision(Decision(Action(ActionType.TAP, target_id="target")))
    controller.move(RunState.EXECUTING)
    controller.record_execution(ExecutionResult(accepted=True, changed=True))
    assert controller.steps == 1


def test_runtime_recovers_from_guard_rejection_without_losing_the_action_slot():
    class Observer:
        def __init__(self):
            self.calls = 0

        def observe(self):
            self.calls += 1
            return _observation(self.calls)

    class Reasoner:
        def __init__(self):
            self.calls = 0
            self.decisions = [
                Decision(Action(ActionType.TAP, target_id="bad"), "bad target"),
                Decision(Action(ActionType.TAP, target_id="target"), "first real action"),
                Decision(Action(ActionType.TAP, target_id="target"), "second real action"),
                Decision(Action(ActionType.TAP, target_id="target"), "third real action"),
            ]

        def decide(self, context):
            decision = self.decisions[self.calls]
            self.calls += 1
            return decision

    class Executor:
        def __init__(self):
            self.calls = 0

        def execute(self, action):
            self.calls += 1
            return ExecutionResult(True, True)

    class Verifier:
        def __init__(self):
            self.calls = 0

        def verify(self, goal, before, decision, result, after):
            self.calls += 1
            return result.accepted and result.changed and self.calls == 4

    observer = Observer()
    reasoner = Reasoner()
    executor = Executor()
    verifier = Verifier()
    runtime = Runtime(Goal("finish"), observer, reasoner, executor, verifier, max_steps=3)
    result = runtime.run()

    assert result.status is RunStatus.SUCCEEDED
    assert result.steps == 3
    assert reasoner.calls == 4
    assert executor.calls == 3
    assert verifier.calls == 4


def test_android_wait_is_non_progress_instead_of_unsupported_execution():
    adapter = AndroidBridgeAdapter.__new__(AndroidBridgeAdapter)
    result = adapter.execute(Action(ActionType.WAIT))
    assert result.accepted is False
    assert result.changed is False
    assert result.error is None
