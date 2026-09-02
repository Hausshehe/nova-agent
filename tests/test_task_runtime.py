from __future__ import annotations

from dataclasses import dataclass

from agent.core import Action, ActionType, Decision, ExecutionResult, UIElement, WorldState
from agent.task_runtime import TaskExecutor


@dataclass
class FakeBridge:
    observed: int = 0
    executed: int = 0

    def observe(self) -> WorldState:
        self.observed += 1
        return WorldState(
            observation_id=str(self.observed),
            elements=(UIElement(id="finish", text="Finish", clickable=True),),
        )

    def execute(self, action: Action) -> ExecutionResult:
        self.executed += 1
        return ExecutionResult(True, True)

    def wait_for_fresh_observation(self, previous: WorldState, timeout: float) -> WorldState:
        self.observed += 1
        return WorldState(
            observation_id=str(self.observed),
            elements=(),
        )


class FinishPlanner:
    def decide(self, context):
        return Decision(
            Action(ActionType.CLICK, context.candidates[0].target),
            rationale="test decision",
        )


def test_task_executor_establishes_high_level_task_boundary():
    bridge = FakeBridge()
    runtime = TaskExecutor(bridge=bridge, planner=FinishPlanner(), max_steps=1)

    assert runtime.run("Tap Finish") is True
    assert bridge.observed >= 2
    assert bridge.executed == 1


def test_task_executor_owns_initial_observation():
    bridge = FakeBridge()
    runtime = TaskExecutor(bridge=bridge, planner=FinishPlanner(), max_steps=1)

    assert bridge.observed == 0
    assert runtime.run("Tap Finish") is True
    assert bridge.observed == 2


def test_task_executor_preserves_navigation_configuration():
    bridge = FakeBridge()
    planner = FinishPlanner()
    runtime = TaskExecutor(
        bridge=bridge,
        planner=planner,
        max_steps=7,
        settle_timeout=1.25,
    )

    assert runtime.max_steps == 7
    assert runtime.settle_timeout == 1.25
    assert runtime.planner is planner
    assert runtime.bridge is bridge
