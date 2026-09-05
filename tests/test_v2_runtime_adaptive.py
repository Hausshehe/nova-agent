from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, UiElement, RunStatus
from nova_core.runtime import Runtime


class Observer:
    def __init__(self, observation):
        self.observation = observation
        self.calls = 0

    def observe(self):
        self.calls += 1
        return self.observation


class Reasoner:
    def __init__(self, decisions):
        self.decisions = iter(decisions)
        self.contexts = []

    def decide(self, context):
        self.contexts.append(context)
        decision = next(self.decisions)
        if isinstance(decision, Exception):
            raise decision
        return decision


class Executor:
    def __init__(self):
        self.actions = []

    def execute(self, action):
        self.actions.append(action)
        return ExecutionResult(True, True)


class Verifier:
    def verify(self, goal, before, decision, result, after):
        return True


def test_invalid_model_decision_is_bounded_recovery_not_immediate_failure():
    observation = Observation(
        "pkg", "activity", (UiElement("go", text="Go", clickable=True, enabled=True),), 1
    )
    observer = Observer(observation)
    reasoner = Reasoner([
        ValueError("tap target is not available in the current observation"),
        Decision(Action(ActionType.TAP, "go"), "retry from fresh evidence"),
    ])
    executor = Executor()
    runtime = Runtime(
        Goal("Go"), observer, reasoner, executor, Verifier(), max_steps=1, max_invalid_decisions=1
    )

    result = runtime.run()

    assert result.status is RunStatus.SUCCEEDED
    assert result.steps == 1
    assert len(reasoner.contexts) == 2
    assert reasoner.contexts[1].evidence.rejected_actions
    assert observer.calls >= 3


def test_invalid_model_decision_stops_after_recovery_budget():
    observation = Observation("pkg", "activity", (), 1)
    runtime = Runtime(
        Goal("Impossible"),
        Observer(observation),
        Reasoner([ValueError("bad 1"), ValueError("bad 2")]),
        Executor(),
        Verifier(),
        max_steps=1,
        max_invalid_decisions=1,
    )

    result = runtime.run()

    assert result.status is RunStatus.FAILED
    assert result.error == "bad 2"
