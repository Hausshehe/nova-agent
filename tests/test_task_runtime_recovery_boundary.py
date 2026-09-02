from agent.core import Action, ActionType, Decision, ExecutionResult, UIElement, WorldState
from agent.reasoning_context import build_reasoning_context
from agent.task_runtime import TaskExecutor


class RecoveryBridge:
    def __init__(self):
        self.state = WorldState(
            package="nova",
            observation_id="before",
            elements=(
                UIElement("wrong", text="Wrong", clickable=True),
                UIElement("retry", text="Retry", clickable=True),
            ),
        )
        self.executed = []

    def observe(self):
        return self.state

    def execute(self, action):
        self.executed.append(action)
        if action.target.element_id == "wrong":
            self.state = WorldState(
                package="nova",
                observation_id="after-failure",
                elements=(UIElement("retry", text="Retry", clickable=True),),
            )
            return ExecutionResult(False, False, error="rejected")
        self.state = WorldState(
            package="nova",
            observation_id="done",
            elements=(UIElement("done", text="Recovery completed"),),
        )
        return ExecutionResult(True, True)

    def wait_for_fresh_observation(self, previous, timeout):
        return self.state


class RecoveryPlanner:
    def __init__(self):
        self.calls = 0

    def decide(self, context):
        self.calls += 1
        target = context.candidates[0].target
        return Decision(Action(ActionType.CLICK, target), "normal plan")


class SpyRecoveryEngine:
    def __init__(self):
        self.calls = 0
        self.recoveries = 0

    def reset(self):
        self.recoveries = 0

    def recover(self, goal, state, history, planner):
        self.calls += 1
        self.recoveries += 1
        context = build_reasoning_context(goal, state, history)
        target = next(
            candidate.target
            for candidate in context.candidates
            if candidate.target and candidate.target.element_id == "retry"
        )
        return Decision(Action(ActionType.CLICK, target), "recovery plan")


def test_task_executor_routes_failed_action_through_recovery_engine():
    bridge = RecoveryBridge()
    planner = RecoveryPlanner()
    recovery = SpyRecoveryEngine()
    runtime = TaskExecutor(
        bridge=bridge,
        planner=planner,
        recovery_engine=recovery,
        max_steps=2,
    )

    assert runtime.run("Recovery completed") is True
    assert recovery.calls == 1
    assert len(bridge.executed) == 2
    assert bridge.executed[0].target.element_id == "wrong"
    assert bridge.executed[1].target.element_id == "retry"
