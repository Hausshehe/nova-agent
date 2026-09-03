from __future__ import annotations

from dataclasses import dataclass

from agent.core import Action, ActionType, Decision, ExecutionResult, UIElement, WorldState
from agent.runtime import create_task_runtime


def state(status: str, observation_id: str) -> WorldState:
    return WorldState(
        package="test",
        activity="Main",
        observation_id=observation_id,
        elements=(
            UIElement("start", "Multi-Step Test", clickable=True),
            UIElement("continue", "Continue Multi-Step", clickable=True),
            UIElement("finish", "Finish Multi-Step", clickable=True),
            UIElement("status", status),
        ),
    )


@dataclass
class Bridge:
    actions: list[Action]

    def __post_init__(self):
        self.observation_number = 0

    def observe(self):
        if not self.actions:
            return state("Multi-Step ready", "1")
        last = self.actions[-1].target.element_id
        if last == "finish":
            return state("Complete the previous steps first", "2")
        if last == "continue":
            return state("Start a Multi-Step Test first", "3")
        return WorldState(
            package="test", activity="Main", observation_id="4",
            elements=(UIElement("status", "Multi-Step Test completed"),),
        )

    def execute(self, action: Action):
        self.actions.append(action)
        return ExecutionResult(True, True)

    def wait_for_fresh_observation(self, previous, timeout=2.0):
        return self.observe()


class Planner:
    def __init__(self):
        self.calls = 0

    def decide(self, context):
        self.calls += 1
        target = {1: "finish", 2: "continue", 3: "continue", 4: "start"}[self.calls]
        return Decision(
            Action(ActionType.CLICK, next(c.target for c in context.candidates if c.target and c.target.element_id == target)),
            "test",
        )


def test_clean_runtime_blocks_repeated_action_in_same_state():
    bridge = Bridge([])
    planner = Planner()
    runtime = create_task_runtime(bridge, reasoning_provider=planner, max_steps=4)

    # The fake planner deliberately proposes Finish, Continue, Continue, Start.
    # The runtime must block the second Continue before Android receives it.
    # Because the planner does not adapt after the block, the task must stop.
    assert runtime.run("Tap Finish Multi-Step") is False
    assert [a.target.element_id for a in bridge.actions] == ["finish", "continue"]
    assert runtime.runtime_state.history[2]["accepted"] is False
    assert runtime.runtime_state.history[2]["task_effect"] == "blocked"


def test_action_goal_is_not_satisfied_by_a_preexisting_button():
    bridge = Bridge([])
    runtime = create_task_runtime(bridge, reasoning_provider=Planner(), max_steps=1)
    assert runtime.run("Tap Finish Multi-Step") is False
    assert len(bridge.actions) == 1
