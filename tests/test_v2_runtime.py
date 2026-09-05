import pytest

from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, RunStatus, UiElement
from nova_core.reasoning import ReasoningContext
from nova_core.runtime import Runtime
from nova_core.state_machine import RunState


class FakeObserver:
    def __init__(self):
        self.calls = 0

    def observe(self):
        self.calls += 1
        return Observation("pkg", "MainActivity", elements=(UiElement(id="button", text="Button", clickable=True, enabled=True),), revision=self.calls)


class FreshFakeObserver(FakeObserver):
    def __init__(self):
        super().__init__()
        self.fresh_calls = 0

    def observe_fresh(self, previous):
        self.fresh_calls += 1
        return Observation("pkg", "MainActivity", elements=(UiElement(id="button", text="Button", clickable=True, enabled=True),), revision=previous.revision + 1)


class FakeReasoner:
    def __init__(self):
        self.calls = 0
        self.contexts = []

    def decide(self, context: ReasoningContext):
        self.calls += 1
        self.contexts.append(context)
        return Decision(Action(ActionType.TAP, target_id="button"), reason=context.goal.text)


class RejectingReasoner:
    def decide(self, context: ReasoningContext):
        raise ValueError("no safe target matches the goal")


class ProviderFailureReasoner:
    def decide(self, context: ReasoningContext):
        raise RuntimeError("reasoning provider failed: Groq request failed with HTTP 429")


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
    for _ in range(20):
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


def test_runtime_uses_fresh_observer_when_available_for_verification():
    observer = FreshFakeObserver()
    reasoner = FakeReasoner()
    executor = FakeExecutor()
    verifier = FakeVerifier()
    runtime = Runtime(Goal("tap button"), observer, reasoner, executor, verifier, max_steps=1)

    advance_to_terminal(runtime)

    assert runtime.controller.state is RunState.SUCCEEDED
    assert observer.calls == 1
    assert observer.fresh_calls == 1
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


def test_reasoner_receives_empty_history_on_first_decision():
    observer = FakeObserver()
    reasoner = FakeReasoner()
    runtime = Runtime(Goal("tap button"), observer, reasoner, FakeExecutor(), FakeVerifier(), max_steps=1)

    runtime.run()

    assert len(reasoner.contexts) == 1
    assert reasoner.contexts[0].history == ()


def test_reasoner_receives_previous_attempt_history_after_recovery_cycle():
    observer = FakeObserver()
    reasoner = FakeReasoner()
    runtime = Runtime(Goal("recover"), observer, reasoner, FakeExecutor(), FakeVerifier(achieved=False), max_steps=2)

    runtime.run()

    assert len(reasoner.contexts) == 2
    assert len(reasoner.contexts[1].history) == 1
    assert reasoner.contexts[1].history[0].decision.action.target_id == "button"
    assert reasoner.contexts[1].history[0].execution.accepted is True
    assert reasoner.contexts[1].history[0].execution.changed is True


def test_runtime_passes_post_action_observation_to_verifier():
    class ObservationVerifier:
        def __init__(self):
            self.after = None

        def verify(self, goal, before, decision, result, after):
            self.after = after
            return True

    observer = FakeObserver()
    verifier = ObservationVerifier()
    runtime = Runtime(Goal("done"), observer, FakeReasoner(), FakeExecutor(), verifier, max_steps=1)

    runtime.run()

    assert verifier.after.revision == 2


def test_runtime_turns_reasoning_rejection_into_bounded_terminal_failure():
    observer = FakeObserver()
    executor = FakeExecutor()
    runtime = Runtime(Goal("Open Navigation"), observer, RejectingReasoner(), executor, FakeVerifier(), max_steps=3, max_invalid_decisions=2)

    result = runtime.run()

    assert result.status is RunStatus.FAILED
    assert result.steps == 0
    assert result.error == "no safe target matches the goal"
    assert executor.calls == 0


def test_runtime_turns_provider_failure_into_terminal_failure():
    observer = FakeObserver()
    executor = FakeExecutor()
    runtime = Runtime(Goal("Finish Multi-Step Test"), observer, ProviderFailureReasoner(), executor, FakeVerifier(), max_steps=3)

    result = runtime.run()

    assert result.status is RunStatus.FAILED
    assert result.steps == 0
    assert result.error == "reasoning provider failed: Groq request failed with HTTP 429"
    assert executor.calls == 0
