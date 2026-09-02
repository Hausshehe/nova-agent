from __future__ import annotations

from dataclasses import dataclass

from agent.action_executor import ActionExecutor
from agent.core import Action, ActionType, Decision, ExecutionResult, Target, TransitionVerifier, UIElement, WorldState
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


def test_task_executor_owns_current_observation_after_action_refresh():
    bridge = FakeBridge()
    runtime = TaskExecutor(bridge=bridge, planner=FinishPlanner(), max_steps=1)

    assert runtime.run("Tap Finish") is True
    assert runtime.current_state is not None
    assert runtime.current_state.observation_id == "2"


def test_task_executor_owns_history_and_step_progression():
    bridge = FakeBridge()
    runtime = TaskExecutor(bridge=bridge, planner=FinishPlanner(), max_steps=1)

    assert runtime.run("Tap Finish") is True
    assert runtime.current_step == 1
    assert len(runtime.history) == 1
    assert runtime.history[0]["step"] == 1
    assert runtime.history[0]["accepted"] is True
    assert runtime.history[0]["verified"] is True


def test_task_executor_resets_lifecycle_state_for_each_run():
    bridge = FakeBridge()
    runtime = TaskExecutor(bridge=bridge, planner=FinishPlanner(), max_steps=1)

    assert runtime.run("Tap Finish") is True
    first_state_id = runtime.current_state.observation_id
    assert runtime.run("Tap Finish") is True

    assert runtime.current_step == 1
    assert len(runtime.history) == 1
    assert runtime.current_state is not None
    assert runtime.current_state.observation_id != first_state_id


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


def test_action_executor_executes_and_verifies_transition():
    bridge = FakeBridge()
    executor = ActionExecutor(bridge=bridge, verifier=TransitionVerifier(), settle_timeout=1.25)
    previous = bridge.observe()
    action = Action(ActionType.CLICK, Target(element_id="finish", text="Finish"))

    result, after, verified = executor.execute(action, previous)

    assert result.accepted is True
    assert result.changed is True
    assert after is not None
    assert after.observation_id == "2"
    assert verified is True
    assert bridge.executed == 1


def test_task_executor_uses_action_executor_boundary():
    bridge = FakeBridge()
    runtime = TaskExecutor(bridge=bridge, planner=FinishPlanner(), max_steps=1)

    assert isinstance(runtime.action_executor, ActionExecutor)
    assert runtime.action_executor.bridge is bridge
    assert runtime.action_executor.verifier is runtime.verifier
    assert runtime.action_executor.settle_timeout == runtime.settle_timeout
