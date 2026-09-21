from nova_core.capability_runtime import build_capability_runtime
from nova_core.models import ExecutionResult, Goal, Observation
from nova_core.reasoning import ReasoningContext


class FakeObserver:
    def observe(self):
        return Observation(package="nova", activity="MainActivity", revision=1)


class FakeExecutor:
    def execute(self, action):
        return ExecutionResult(accepted=True, changed=True)


class FakeVerifier:
    def verify(self, goal, before, decision, result, after):
        return True


def _action_responder(prompt):
    return {
        "action_type": "back",
        "reason": "capability-routed action",
    }


def _planning_responder(prompt):
    return {"steps": ["advance the current mission"]}


def test_runtime_factory_connects_action_selection_to_runtime():
    runtime = build_capability_runtime(
        Goal("Finish the mission"),
        FakeObserver(),
        FakeExecutor(),
        FakeVerifier(),
        action_responders=[("cerebras", _action_responder)],
        max_steps=1,
    )

    result = runtime.run()

    assert result.status.value == "succeeded"
    assert result.steps == 1


def test_runtime_factory_connects_planning_through_the_same_capability_boundary():
    runtime = build_capability_runtime(
        Goal("Finish the mission"),
        FakeObserver(),
        FakeExecutor(),
        FakeVerifier(),
        action_responders=[("cerebras", _action_responder)],
        planning_responders=[("cerebras", _planning_responder)],
        max_steps=1,
    )

    assert runtime.planner is not None
    context = ReasoningContext(Goal("Finish the mission"), Observation(package="nova", activity="MainActivity", revision=1))
    assert runtime.planner.plan(context).steps[0].description == "advance the current mission"


def test_runtime_factory_does_not_fabricate_unprovisioned_capabilities():
    runtime = build_capability_runtime(
        Goal("Finish the mission"),
        FakeObserver(),
        FakeExecutor(),
        FakeVerifier(),
        action_responders=[("cerebras", _action_responder)],
    )

    from nova_core.planning import GoalPlanner
    assert isinstance(runtime.planner, GoalPlanner)
