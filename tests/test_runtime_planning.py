from nova_core.llm_planner import LLMPlanner
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


class FreshFakeObserver(FakeObserver):
    """FreshObserver implementation that records post-action observations."""

    def __init__(self):
        super().__init__()
        self.fresh_calls = 0
        self.fresh_previous_revisions = []

    def observe_fresh(self, previous):
        self.fresh_calls += 1
        self.fresh_previous_revisions.append(previous.revision)
        return self.observe()


class DisappearingTargetObserver(FreshFakeObserver):
    """Fresh evidence removes the accepted-but-unchanged action target."""

    def observe_fresh(self, previous):
        self.fresh_calls += 1
        self.fresh_previous_revisions.append(previous.revision)
        self.revision += 1
        return Observation(
            package="com.example.app",
            activity="MainActivity",
            revision=self.revision,
            elements=(),
        )


class FakeExecutor:
    def __init__(self, changed=True):
        self.changed = changed
        self.calls = 0

    def execute(self, action):
        self.calls += 1
        return ExecutionResult(accepted=True, changed=self.changed)


class FakeVerifier:
    def verify(self, goal, before, decision, result, after):
        return False


class FakeReasoner:
    def decide(self, context: ReasoningContext):
        assert context.plan is not None
        assert context.plan.current is not None
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


class ReplayThenFallbackPlanner(RecordingPlanner):
    def replan(self, context, previous):
        self.replan_calls += 1
        return Plan(
            (
                PlanStep(previous.current.description),
                PlanStep("fallback intent"),
            ),
            revision=previous.revision + 1,
        )


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


def test_runtime_allows_one_unchanged_retry_before_replanning():
    planner = RecordingPlanner()
    runtime = Runtime(
        Goal("Finish the task"), FakeObserver(), FakeReasoner(), FakeExecutor(changed=False), FakeVerifier(),
        max_steps=2, max_invalid_decisions=3, max_replans=1, planner=planner,
    )

    result = runtime.run()

    assert result.error == "replan budget exhausted"
    assert planner.plan_calls == 1
    assert planner.replan_calls == 1
    assert runtime.replans == 1


def test_runtime_replans_after_two_unchanged_executions():
    planner = RecordingPlanner()
    runtime = Runtime(
        Goal("Finish the task"), FakeObserver(), FakeReasoner(), FakeExecutor(changed=False), FakeVerifier(),
        max_steps=3, max_invalid_decisions=3, max_replans=1, planner=planner,
    )

    result = runtime.run()

    assert result.error == "replan budget exhausted"
    assert planner.plan_calls == 1
    assert planner.replan_calls == 1
    assert runtime.replans == 1
    assert runtime.brain.plan is not None
    assert runtime.brain.plan.revision == 1


def test_runtime_replans_immediately_when_fresh_evidence_removes_unchanged_target():
    planner = RecordingPlanner()
    observer = DisappearingTargetObserver()
    runtime = Runtime(
        Goal("Finish the task"), observer, FakeReasoner(), FakeExecutor(changed=False), FakeVerifier(),
        max_steps=1, max_replans=1, planner=planner,
    )

    result = runtime.run()

    assert result.error == "step budget exhausted"
    assert planner.plan_calls == 1
    assert planner.replan_calls == 0
    assert runtime.replans == 0
    assert runtime._replan_requested is True

    runtime.controller.max_steps = 2
    runtime.run()

    assert planner.replan_calls == 1
    assert runtime.replans == 1


def test_runtime_skips_exact_replay_at_start_of_replanned_plan():
    planner = ReplayThenFallbackPlanner()
    runtime = Runtime(
        Goal("Finish the task"), FakeObserver(), FakeReasoner(), FakeExecutor(changed=False), FakeVerifier(),
        max_steps=3, max_invalid_decisions=3, max_replans=1, planner=planner,
    )

    result = runtime.run()

    assert result.error == "replan budget exhausted"
    assert runtime.brain.plan is not None
    assert runtime.brain.plan.revision == 1
    assert runtime.brain.plan.current is not None
    assert runtime.brain.plan.current.description == "fallback intent"


def test_runtime_uses_fresh_observation_after_accepted_unchanged_action():
    planner = RecordingPlanner()
    observer = FreshFakeObserver()
    executor = FakeExecutor(changed=False)
    runtime = Runtime(
        Goal("Finish the task"), observer, FakeReasoner(), executor, FakeVerifier(),
        max_steps=2, max_replans=1, planner=planner,
    )

    result = runtime.run()

    assert result.error == "replan budget exhausted"
    assert observer.fresh_calls == executor.calls
    assert observer.fresh_previous_revisions == list(range(1, 2 * executor.calls, 2))
    assert observer.fresh_calls > 0


def test_runtime_uses_llm_planner_for_initial_plan_and_f7_replan():
    prompts = []
    responses = iter(
        (
            '{"steps":["first intent","second intent"]}',
            '{"steps":["recovered intent"]}',
        )
    )

    def complete(prompt: str) -> str:
        prompts.append(prompt)
        return next(responses)

    planner = LLMPlanner(complete)
    runtime = Runtime(
        Goal("Finish the task"),
        FakeObserver(),
        FakeReasoner(),
        FakeExecutor(changed=False),
        FakeVerifier(),
        max_steps=3,
        max_replans=1,
        planner=planner,
    )

    result = runtime.run()

    assert result.error == "replan budget exhausted"
    assert len(prompts) == 2
    assert runtime.replans == 1
    assert runtime.brain.plan is not None
    assert runtime.brain.plan.revision == 1
    assert runtime.brain.plan.current is not None
    assert runtime.brain.plan.current.description == "recovered intent"
    assert '"first intent"' in prompts[1]
    assert '"second intent"' in prompts[1]
    assert '"last_execution_changed":false' in prompts[1]
    assert '"unchanged_observation_count"' in prompts[1]
