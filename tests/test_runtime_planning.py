from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, UiElement
from nova_core.planning import Plan, PlanStep
from nova_core.reasoning import ReasoningContext
from nova_core.runtime import Runtime
from nova_core.state_machine import RunState


class FakeObserver:
    def __init__(self):
        self.revision = 0

    def observe(self):
        self.revision += 1
        return Observation(
            package="com.example.app",
            activity="MainActivity",
            revision=self.revision,
            elements=(UiElement(id="button", text="Continue", clickable=True),),
        )


class FakeExecutor:
    def __init__(self, changed=True):
        self.changed = changed

    def execute(self, action):
        return ExecutionResult(accepted=True, changed=self.changed)


class FakeVerifier:
    def verify(self, goal, before, decision, result, after):
        return False


class FakeReasoner:
    def decide(self, context: ReasoningContext):
        assert context.plan is not None
        return Decision(Action(ActionType.TAP, target_id="button"), reason=context.plan.current.description)


class RecordingPlanner:
    def __init__(self):
        self.plan_calls = 0
        self.replan_calls = 0

    def plan(self, context):
        self.plan_calls += 1
        return Plan((PlanStep("first intent"), PlanStep("second intent")))

    def replan(self, context, previous):
        self.replan_calls += 1
        return Plan((PlanStep("recovered intent"),), revision=previous.revision + 1)


def test_runtime_creates_plan_and_advances_after_verified_progress():
    planner = RecordingPlanner()
    runtime = Runtime(
        Goal("Finish the task"), FakeObserver(), FakeReasoner(), FakeExecutor(), FakeVerifier(),
        max_steps=2, planner=planner,
    )

    runtime.run()

    assert planner.plan_calls == 1
    assert planner.replan_calls == 0
    assert runtime.brain.plan is not None
    assert runtime.brain.plan.cursor == 2
    assert runtime.brain.state is RunState.FAILED


def test_runtime_requests_replan_after_unchanged_execution():
    planner = RecordingPlanner()
    runtime = Runtime(
        Goal("Finish the task"), FakeObserver(), FakeReasoner(), FakeExecutor(changed=False), FakeVerifier(),
        max_steps=2, max_invalid_decisions=3, planner=planner,
    )

    runtime.run()

    assert planner.plan_calls == 1
    assert planner.replan_calls == 1
    assert runtime.brain.plan is not None
    assert runtime.brain.plan.revision == 1
