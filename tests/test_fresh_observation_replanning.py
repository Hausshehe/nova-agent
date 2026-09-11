from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, RunStatus, UiElement
from nova_core.planning import Plan, PlanStep
from nova_core.runtime import Runtime


class SequenceObserver:
    def __init__(self):
        self.revision = 0

    def observe(self):
        self.revision += 1
        if self.revision == 1:
            elements = (
                UiElement(id="stale-future-intent", text="State 1", clickable=True),
            )
        else:
            elements = (
                UiElement(id="freshly-observed-intent", text=f"State {self.revision} fresh", clickable=True),
                UiElement(id="another-stale-intent", text=f"State {self.revision} legacy", clickable=True),
            )
        return Observation(
            package="com.example.app",
            activity="MainActivity",
            revision=self.revision,
            elements=elements,
        )


class RecordingExecutor:
    def __init__(self):
        self.targets = []

    def execute(self, action):
        self.targets.append(action.target_id)
        return ExecutionResult(accepted=True, changed=True)


class PlanReasoner:
    def decide(self, context):
        assert context.plan is not None and context.plan.current is not None
        return Decision(
            Action(ActionType.TAP, target_id=context.plan.current.description),
            reason=context.plan.current.description,
        )


class NeverCompleteVerifier:
    def verify(self, goal, before, decision, result, after):
        return False


class FreshPlanProvider:
    def __init__(self):
        self.plan_calls = 0
        self.replan_calls = 0

    def plan(self, context):
        self.plan_calls += 1
        return Plan((PlanStep("stale-future-intent"), PlanStep("another-stale-intent")), revision=0)

    def replan(self, context, previous):
        self.replan_calls += 1
        return Plan((PlanStep("freshly-observed-intent"),), revision=previous.revision + 1)


def test_llm_style_runtime_replans_after_successful_progress_from_fresh_observation():
    observer = SequenceObserver()
    executor = RecordingExecutor()
    planner = FreshPlanProvider()
    runtime = Runtime(
        Goal("Finish the task"),
        observer,
        PlanReasoner(),
        executor,
        NeverCompleteVerifier(),
        max_steps=2,
        max_replans=1,
        planner=planner,
        replan_after_progress=True,
    )

    result = runtime.run()

    assert result.status is RunStatus.FAILED
    assert result.error == "step budget exhausted"
    assert result.steps == 2
    assert planner.plan_calls == 1
    assert planner.replan_calls == 1
    assert executor.targets == ["stale-future-intent", "freshly-observed-intent"]
    assert runtime.brain.plan is not None
    assert runtime.brain.plan.revision == 1


def test_legacy_plans_still_advance_without_fresh_replanning_mode():
    observer = SequenceObserver()
    executor = RecordingExecutor()
    planner = FreshPlanProvider()
    runtime = Runtime(
        Goal("Finish the task"),
        observer,
        PlanReasoner(),
        executor,
        NeverCompleteVerifier(),
        max_steps=2,
        max_replans=1,
        planner=planner,
        replan_after_progress=False,
    )

    result = runtime.run()

    assert result.status is RunStatus.FAILED
    assert result.error == "step budget exhausted"
    assert planner.plan_calls == 1
    assert planner.replan_calls == 0
    assert executor.targets == ["stale-future-intent", "another-stale-intent"]
