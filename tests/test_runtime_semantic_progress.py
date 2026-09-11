from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation
from nova_core.planning import Plan, PlanStep
from nova_core.runtime import Runtime
from nova_core.run_controller import RunController


class StaticObserver:
    def __init__(self):
        self.observation = Observation("pkg", "MainActivity", revision=1)

    def observe(self):
        return self.observation


class StaticReasoner:
    def decide(self, context):
        return Decision(Action(ActionType.TAP, target_id="button"), reason=context.plan.current.description)


class ChangedExecutor:
    def execute(self, action):
        return ExecutionResult(True, True)


class NeverGoalVerifier:
    def verify(self, goal, before, decision, result, after):
        return False


class FixedIntentVerifier:
    def __init__(self, achieved):
        self.achieved = achieved
        self.goals = []

    def verify(self, goal, before, decision, result, after):
        self.goals.append(goal.text)
        return self.achieved


class SingleStepPlanner:
    def plan(self, context):
        return Plan((PlanStep("Open the target screen"),), revision=0)

    def replan(self, context, previous):
        return Plan((PlanStep("Open the target screen"),), revision=previous.revision + 1)


def _runtime(intent_achieved):
    intent_verifier = FixedIntentVerifier(intent_achieved)
    runtime = Runtime(
        Goal("Complete the mission"),
        StaticObserver(),
        StaticReasoner(),
        ChangedExecutor(),
        NeverGoalVerifier(),
        max_steps=1,
        planner=SingleStepPlanner(),
        intent_verifier=intent_verifier,
    )
    return runtime, intent_verifier


def test_changed_action_does_not_advance_plan_without_semantic_completion():
    runtime, intent_verifier = _runtime(False)

    runtime.run()

    assert runtime.brain.plan is not None
    assert runtime.brain.plan.cursor == 0
    assert intent_verifier.goals == ["Open the target screen"]


def test_semantically_completed_intent_advances_plan():
    runtime, intent_verifier = _runtime(True)

    runtime.run()

    assert runtime.brain.plan is not None
    assert runtime.brain.plan.cursor == 1
    assert runtime.brain.plan.complete
    assert intent_verifier.goals == ["Open the target screen"]
