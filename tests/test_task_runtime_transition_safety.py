from __future__ import annotations

from dataclasses import dataclass, field

from agent.core import Action, ActionType, Decision, ExecutionResult, Target, UIElement, WorldState
from agent.task_runtime import TaskExecutor


@dataclass
class StaleScreenBridge:
    """Simulate an external UI transition between planning and physical execution."""

    state_a: WorldState
    state_b: WorldState
    state_c: WorldState
    current: WorldState = field(init=False)
    executions: list[str] = field(default_factory=list)
    stale_rejections: int = 0

    def __post_init__(self) -> None:
        self.current = self.state_a

    def observe(self) -> WorldState:
        return self.current

    def wait_for_fresh_observation(self, previous: WorldState, timeout: float) -> WorldState:
        if self.current == previous:
            raise TimeoutError("no fresh observation")
        return self.current

    def execute(self, action: Action) -> ExecutionResult:
        assert action.target is not None
        target_id = action.target.element_id
        self.executions.append(target_id)

        available_ids = {element.id for element in self.current.elements if element.visible}
        if target_id not in available_ids:
            self.stale_rejections += 1
            return ExecutionResult(False, False, error="stale target")

        if target_id == "continue_a":
            self.current = self.state_b
            return ExecutionResult(True, True)
        if target_id == "continue_b":
            self.current = self.state_c
            return ExecutionResult(True, True)
        return ExecutionResult(False, False, error="unexpected target")


@dataclass
class StaleAwarePlanner:
    bridge: StaleScreenBridge
    calls: int = 0
    planned_observation_ids: list[str] = field(default_factory=list)

    def decide(self, context) -> Decision:
        self.calls += 1
        self.planned_observation_ids.append(context.state.observation_id)

        if self.calls == 1:
            # The planner received state A, but the real UI changes before execution.
            self.bridge.current = self.bridge.state_b
            return Decision(
                Action(ActionType.CLICK, Target("continue_a", text="Continue")),
                rationale="stale-screen safety test",
            )

        assert context.state.observation_id == "B"
        return Decision(
            Action(ActionType.CLICK, Target("continue_b", text="Continue")),
            rationale="re-plan from fresh state",
        )


def _state(observation_id: str, *elements: UIElement) -> WorldState:
    return WorldState(
        package="com.hausshehe.nova",
        activity="com.hausshehe.nova.MainActivity",
        elements=tuple(elements),
        observation_id=observation_id,
    )


def test_task_executor_rejects_stale_target_and_replans_from_fresh_state() -> None:
    state_a = _state(
        "A",
        UIElement("continue_a", text="Continue", clickable=True),
    )
    state_b = _state(
        "B",
        UIElement("continue_b", text="Continue", clickable=True),
    )
    state_c = _state(
        "C",
        UIElement("done", text="Task completed", clickable=False),
    )
    bridge = StaleScreenBridge(state_a, state_b, state_c)
    planner = StaleAwarePlanner(bridge)

    executor = TaskExecutor(
        bridge=bridge,
        planner=planner,
        max_steps=3,
    )

    assert executor.run("Task completed") is True
    assert bridge.stale_rejections == 1
    assert bridge.executions == ["continue_a", "continue_b"]
    assert planner.planned_observation_ids == ["A", "B"]
    assert executor.current_state == state_c

    first = executor.history[0]
    assert first["accepted"] is False
    assert first["verified"] is False
    assert first["error"] == "stale target"

    second = executor.history[1]
    assert second["accepted"] is True
    assert second["verified"] is True
