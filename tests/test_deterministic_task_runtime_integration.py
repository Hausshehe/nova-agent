from agent.core import ActionType, ExecutionResult, UIElement, WorldState
from agent.deterministic_reasoner import DeterministicReasoner
from agent.task_runtime import TaskExecutor


class DeterministicBridge:
    def __init__(self):
        self.state = WorldState(
            package="nova",
            observation_id="before",
            elements=(
                UIElement("wrong", text="Ignore this", clickable=True),
                UIElement("target", text="Open Settings", clickable=True),
            ),
        )
        self.executed = []

    def observe(self):
        return self.state

    def execute(self, action):
        self.executed.append(action)
        assert action.type is ActionType.CLICK
        assert action.target is not None
        assert action.target.element_id == "target"
        self.state = WorldState(
            package="nova",
            observation_id="after",
            elements=(UIElement("settings", text="Settings"),),
        )
        return ExecutionResult(True, True)

    def wait_for_fresh_observation(self, previous, timeout):
        return self.state


def test_deterministic_reasoner_runs_through_task_executor_boundary():
    bridge = DeterministicBridge()
    runtime = TaskExecutor(
        bridge=bridge,
        planner=DeterministicReasoner(),
        max_steps=1,
    )

    assert runtime.run("Open Settings") is True
    assert len(bridge.executed) == 1
    assert bridge.executed[0].target.element_id == "target"
    assert runtime.current_state.observation_id == "after"
    assert runtime.history[0]["verified"] is True


def test_deterministic_reasoner_preserves_global_actions_through_task_runtime():
    class BackBridge(DeterministicBridge):
        def execute(self, action):
            self.executed.append(action)
            assert action.type is ActionType.BACK
            self.state = WorldState(
                package="nova",
                observation_id="after-back",
                elements=(UIElement("home", text="Home"),),
            )
            return ExecutionResult(True, True)

    bridge = BackBridge()
    runtime = TaskExecutor(
        bridge=bridge,
        planner=DeterministicReasoner(),
        max_steps=1,
    )

    assert runtime.run("Go back") is True
    assert bridge.executed[0].type is ActionType.BACK
    assert runtime.history[0]["verified"] is True
