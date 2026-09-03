from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation
from nova_core.ports import Executor, FreshObserver, Observer, Reasoner, Verifier


class FakeObserver:
    def observe(self) -> Observation:
        return Observation(package="com.example", activity="MainActivity")


class FakeFreshObserver:
    def observe_fresh(self, previous: Observation) -> Observation:
        return Observation(package=previous.package, activity=previous.activity, revision=previous.revision + 1)


class FakeReasoner:
    def decide(self, goal: Goal, observation: Observation) -> Decision:
        return Decision(action=Action(type=ActionType.WAIT), reason=goal.text)


class FakeExecutor:
    def execute(self, action: Action) -> ExecutionResult:
        return ExecutionResult(accepted=True, changed=True)


class FakeVerifier:
    def verify(
        self,
        goal: Goal,
        before: Observation,
        decision: Decision,
        result: ExecutionResult,
        after: Observation,
    ) -> bool:
        return result.accepted and result.changed and before != after


def test_observer_port_is_structural():
    observer: Observer = FakeObserver()
    assert observer.observe().package == "com.example"


def test_fresh_observer_port_is_structural():
    observer: FreshObserver = FakeFreshObserver()
    before = Observation(package="com.example", activity="MainActivity", revision=1)
    assert observer.observe_fresh(before).revision == 2


def test_reasoner_port_is_structural():
    reasoner: Reasoner = FakeReasoner()
    goal = Goal("wait")
    decision = reasoner.decide(goal, FakeObserver().observe())
    assert decision.action.type is ActionType.WAIT
    assert decision.reason == "wait"


def test_executor_port_is_structural():
    executor: Executor = FakeExecutor()
    result = executor.execute(Action(type=ActionType.WAIT))
    assert result.accepted is True
    assert result.changed is True


def test_verifier_port_is_structural():
    verifier: Verifier = FakeVerifier()
    before = Observation(package="com.example", activity="MainActivity", revision=1)
    after = Observation(package="com.example", activity="MainActivity", revision=2)
    result = ExecutionResult(accepted=True, changed=True)
    assert verifier.verify(Goal("finish"), before, Decision(Action(ActionType.WAIT)), result, after)
