from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, RunStatus
from nova_core.runtime import Runtime
from nova_core.state_machine import RunState


class FakeObserver:
    def __init__(self):
        self.calls = 0

    def observe(self):
        self.calls += 1
        return Observation("pkg", "MainActivity", revision=self.calls)


class FakeReasoner:
    def __init__(self):
        self.calls = 0

    def decide(self, goal, observation):
        self.calls += 1
        return Decision(Action(ActionType.TAP, target_id="button"), reason=goal.text)


class FakeExecutor:
    def __init__(self):
        self.calls = 0

    def execute(self, action):
        self.calls += 1
        return ExecutionResult(accepted=True, changed=True)


class FakeVerifier:
    def __init__(self, achieved=True):
        self.achieved = achieved
        self.calls = 0

    def verify(self, goal, before, decision, result, after):
        self.calls += 1
        return self.achieved


def advance_to_terminal(runtime):
    for _ in range(10):
        runtime.step()
        if runtime.controller.result() is not None:
            return
    raise AssertionError("runtime did not reach a terminal state")


def test_runtime_wires_ports_without_owning_adapter_behavior():
    observer = FakeObserver()
    reasoner = FakeReasoner()
    executor = FakeExecutor()
    verifier = FakeVerifier()
    runtime = Runtime(Goal("tap button"), observer, reasoner, executor, verifier, max_steps=1)

    advance_to_terminal(runtime)

    assert runtime.controller.state is RunState.SUCCEEDED
    assert runtime.controller.result().status is RunStatus.SUCCEEDED
    assert observer.calls == 2
    assert reasoner.calls == 1
    assert executor.calls == 1
    assert verifier.calls == 1


def test_runtime_reobserves_after_unsuccessful_verification_until_budget():
    observer = FakeObserver()
    reasoner = FakeReasoner()
    executor = FakeExecutor()
    verifier = FakeVerifier(achieved=False)
    runtime = Runtime(Goal("finish"), observer, reasoner, executor, verifier, max_steps=2)

    advance_to_terminal(runtime)

    assert runtime.controller.state is RunState.FAILED
    assert runtime.controller.result().status is RunStatus.FAILED
    assert runtime.controller.steps == 2
    assert observer.calls == 4
    assert reasoner.calls == 2
    assert executor.calls == 2
    assert verifier.calls == 2


def test_runtime_executes_at_most_one_action_per_step():
    observer = FakeObserver()
    reasoner = FakeReasoner()
    executor = FakeExecutor()
    verifier = FakeVerifier()
    runtime = Runtime(Goal("tap"), observer, reasoner, executor, verifier)

    for _ in range(3):
        runtime.step()

    assert executor.calls == 0
    runtime.step()
    assert executor.calls == 1


def test_runtime_run_returns_success_without_manual_stepping():
    observer = FakeObserver()
    reasoner = FakeReasoner()
    executor = FakeExecutor()
    verifier = FakeVerifier()
    runtime = Runtime(Goal("tap button"), observer, reasoner, executor, verifier, max_steps=1)

    result = runtime.run()

    assert result.status is RunStatus.SUCCEEDED
    assert result.steps == 1
    assert executor.calls == 1


def test_runtime_run_is_bounded_when_verification_never_succeeds():
    observer = FakeObserver()
    reasoner = FakeReasoner()
    executor = FakeExecutor()
    verifier = FakeVerifier(achieved=False)
    runtime = Runtime(Goal("never finish"), observer, reasoner, executor, verifier, max_steps=2)

    result = runtime.run()

    assert result.status is RunStatus.FAILED
    assert result.steps == 2
    assert result.error == "step budget exhausted"
    assert executor.calls == 2
