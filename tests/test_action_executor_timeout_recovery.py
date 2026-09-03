from agent.core import Action, ActionType, Decision, ExecutionResult, Target, UIElement, WorldState
from agent.task_runtime import TaskExecutor


class TimeoutThenBlockedProvider:
    def __init__(self):
        self.refresh_calls = 0
        self.observe_calls = 0

    def observe(self):
        self.observe_calls += 1
        if self.observe_calls == 1:
            return self.state("initial", "Ready")
        return self.state("blocked", "Start a Multi-Step Test first")

    def refresh(self, previous):
        self.refresh_calls += 1
        raise TimeoutError("simulated settling race")

    @staticmethod
    def state(observation_id, status):
        return WorldState(
            package="test",
            activity="Main",
            observation_id=observation_id,
            elements=(
                UIElement(id="continue", text="Continue", clickable=True),
                UIElement(id="status", text=status, clickable=False),
            ),
        )


class RepeatContinuePlanner:
    def __init__(self):
        self.calls = 0

    def decide(self, context):
        self.calls += 1
        target = next(c.target for c in context.candidates if c.target and c.target.element_id == "continue")
        return Decision(Action(ActionType.CLICK, target), rationale="repeat for regression")


class RecordingBridge:
    def __init__(self):
        self.executed = 0

    def observe(self):
        return TimeoutThenBlockedProvider.state("bridge", "Ready")

    def execute(self, action):
        self.executed += 1
        return ExecutionResult(True, True)


def test_observation_timeout_never_restarts_recovery_from_stale_state():
    provider = TimeoutThenBlockedProvider()
    bridge = RecordingBridge()
    planner = RepeatContinuePlanner()
    runtime = TaskExecutor(
        bridge=bridge,
        planner=planner,
        observation_provider=provider,
        max_steps=2,
    )

    assert runtime.run("Tap Finish") is False
    assert bridge.executed == 1
    assert runtime.history[0]["task_effect"] == "blocked"
    assert runtime.history[1]["accepted"] is False
    assert "action guard blocked" in runtime.history[1]["error"]
