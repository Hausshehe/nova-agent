from nova_core.adapters.android import AndroidBridgeAdapter
from nova_core.models import ActionType, Decision, ExecutionResult, Goal, Observation, RunStatus, UiElement
from nova_core.reasoning import ReasoningContext
from nova_core.runtime import Runtime


class FakeBridge:
    def __init__(self):
        self.states = [
            type("State", (), {
                "package": "com.hausshehe.nova",
                "activity": "MainActivity",
                "elements": [type("E", (), {"id": "button", "text": "Test", "content_description": "", "clickable": True, "enabled": True, "visible": True})()],
            })(),
            type("State", (), {
                "package": "com.hausshehe.nova",
                "activity": "MainActivity",
                "elements": [type("E", (), {"id": "done", "text": "Done", "content_description": "", "clickable": False, "enabled": True, "visible": True})()],
            })(),
        ]
        self.executions = []

    def observe(self):
        return self.states[0]

    def wait_for_fresh_observation(self, previous, timeout, poll_seconds):
        return self.states[1]

    def execute(self, action):
        self.executions.append(action)
        return ExecutionResult(True, True)


class Reasoner:
    def decide(self, context: ReasoningContext):
        assert context.observation.package == "com.hausshehe.nova"
        return Decision(
            action=__import__("nova_core.models", fromlist=["Action"]).Action(
                ActionType.TAP, target_id="button"
            )
        )


def test_android_adapter_and_runtime_compose_with_deterministic_verifier():
    bridge = FakeBridge()
    adapter = AndroidBridgeAdapter(bridge)

    def goal_evaluator(goal, observation):
        return any(element.text == "Done" for element in observation.elements)

    from nova_core.adapters.android import AndroidGoalVerifier

    runtime = Runtime(
        Goal("Done"),
        adapter,
        Reasoner(),
        adapter,
        AndroidGoalVerifier(goal_evaluator),
        max_steps=1,
    )

    result = runtime.run()

    assert result.status is RunStatus.SUCCEEDED
    assert result.steps == 1
    assert len(bridge.executions) == 1
    assert bridge.executions[0].type.value == "click"
