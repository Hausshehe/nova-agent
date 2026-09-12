from __future__ import annotations

from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, UiElement
from nova_core.planning import Plan, PlanStep
from nova_core.runtime import Runtime


TARGET = "com.hausshehe.nova:id/recovery_fallback"


class _Observer:
    def __init__(self):
        self.fresh_calls = 0
        self.current = Observation(
            "com.hausshehe.nova",
            "MainActivity",
            (UiElement("com.hausshehe.nova:id/recovery_primary", text="Recovery Primary Action", clickable=True),),
            1,
        )

    def observe(self):
        return self.current

    def observe_fresh(self, previous):
        self.fresh_calls += 1
        self.current = Observation(
            "com.hausshehe.nova",
            "MainActivity",
            (UiElement(TARGET, text="Recovery Fallback Action", clickable=True),),
            previous.revision + 1,
        )
        return self.current


class _Planner:
    def plan(self, context):
        return Plan((PlanStep("tap Recovery Fallback Action"),), revision=0)

    def replan(self, context, previous):
        return Plan((PlanStep("tap Recovery Fallback Action"),), revision=previous.revision + 1)


class _Reasoner:
    def decide(self, context):
        return Decision(Action(ActionType.TAP, target_id=TARGET), reason="tap fallback")


class _Executor:
    def __init__(self):
        self.actions = []

    def execute(self, action):
        self.actions.append(action)
        return ExecutionResult(True, True)


class _Verifier:
    def verify(self, *args):
        return False


def test_runtime_refreshes_live_target_before_rejecting_missing_guard_target():
    observer = _Observer()
    executor = _Executor()
    runtime = Runtime(
        Goal("Complete Recovery"),
        observer,
        _Reasoner(),
        executor,
        _Verifier(),
        max_steps=1,
        planner=_Planner(),
    )

    runtime.step()  # CREATED -> OBSERVING
    runtime.step()  # OBSERVING -> DECIDING + plan
    runtime.step()  # DECIDING -> EXECUTING
    runtime.step()  # EXECUTING -> VERIFYING

    assert observer.fresh_calls == 1
    assert executor.actions == [Action(ActionType.TAP, target_id=TARGET)]
    assert runtime.controller.last_execution == ExecutionResult(True, True)
    assert runtime.controller.observation.elements[0].id == TARGET
