from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, UiElement
from nova_core.planning import Plan, PlanStep
from nova_core.reasoning import ReasoningContext
from nova_core.reasoning_adapter import LLMReasoner
from nova_core.runtime import Runtime
from nova_core.state_machine import RunState


class Observer:
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


class Executor:
    def __init__(self):
        self.calls = 0

    def execute(self, action):
        self.calls += 1
        return ExecutionResult(accepted=True, changed=True)


class Verifier:
    def verify(self, goal, before, decision, result, after):
        return False


class Planner:
    def __init__(self):
        self.plan_calls = 0
        self.replan_calls = 0

    def plan(self, context):
        self.plan_calls += 1
        return Plan((PlanStep("old intent"), PlanStep("next intent")))

    def replan(self, context, previous):
        self.replan_calls += 1
        return Plan((PlanStep("recovered intent"),), revision=previous.revision + 1)


class StaleThenValidReasoner:
    def __init__(self):
        self.calls = 0

    def decide(self, context):
        self.calls += 1
        if self.calls == 1:
            return Decision(Action(ActionType.TAP, target_id="button"), "old plan no longer fits", plan_stale=True)
        return Decision(Action(ActionType.TAP, target_id="button"), "use current UI")


def test_runtime_replans_before_executing_stale_plan():
    planner = Planner()
    executor = Executor()
    runtime = Runtime(
        Goal("Finish the task"), Observer(), StaleThenValidReasoner(), executor, Verifier(),
        max_steps=1, max_replans=1, planner=planner,
    )

    result = runtime.run()

    assert result.status.value == "failed"
    assert result.error == "step budget exhausted"
    assert planner.plan_calls == 1
    assert planner.replan_calls == 1
    assert executor.calls == 1
    assert runtime.brain.plan is not None
    assert runtime.brain.plan.revision == 1


def test_llm_reasoner_preserves_explicit_stale_plan_signal():
    context = ReasoningContext(
        goal=Goal("Finish the task"),
        observation=Observation(
            package="com.example.app",
            activity="MainActivity",
            revision=1,
            elements=(UiElement(id="button", text="Continue", clickable=True),),
        ),
        plan=Plan((PlanStep("old intent"),)),
    )
    reasoner = LLMReasoner(lambda prompt: {
        "action_type": "tap",
        "target_id": "button",
        "reason": "the old plan is stale",
        "plan_status": "stale",
    })

    decision = reasoner.decide(context)

    assert decision.plan_stale is True
    assert decision.action.target_id == "button"
