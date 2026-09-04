from nova_core.adapters.android import AndroidBridgeAdapter, AndroidGoalVerifier
from nova_core.deterministic_reasoner import DeterministicReasoner
from nova_core.models import Action, ActionType, ExecutionResult, Goal, RunStatus
from nova_core.runtime import Runtime


class FakeElement:
    def __init__(self, id, text, clickable=True, enabled=True, visible=True):
        self.id = id
        self.text = text
        self.content_description = ""
        self.clickable = clickable
        self.enabled = enabled
        self.visible = visible


class FakeState:
    def __init__(self, elements):
        self.package = "com.hausshehe.nova"
        self.activity = "MainActivity"
        self.elements = elements


class FakeBridge:
    def __init__(self, states):
        self.states = list(states)
        self.index = 0
        self.executed = []

    def observe(self):
        return self.states[self.index]

    def wait_for_fresh_observation(self, previous, timeout, poll_seconds):
        if self.index + 1 >= len(self.states):
            raise TimeoutError("no fresh state")
        self.index += 1
        return self.states[self.index]

    def execute(self, action):
        self.executed.append(action)
        return ExecutionResult(accepted=True, changed=True)


def test_native_deterministic_reasoner_drives_v2_runtime_to_goal():
    bridge = FakeBridge(
        [
            FakeState([FakeElement("target", "Test Navigation Action")]),
            FakeState([FakeElement("done", "Navigation Completed", clickable=False)]),
        ]
    )
    adapter = AndroidBridgeAdapter(bridge)

    runtime = Runtime(
        Goal("Tap Test Navigation Action"),
        adapter,
        DeterministicReasoner(),
        adapter,
        AndroidGoalVerifier(lambda goal, observation: any(e.text == "Navigation Completed" for e in observation.elements)),
        max_steps=1,
    )

    result = runtime.run()

    assert result.status is RunStatus.SUCCEEDED
    assert result.steps == 1
    assert len(bridge.executed) == 1
    assert bridge.executed[0].type is ActionType.TAP
    assert bridge.executed[0].target.element_id == "target"


def test_native_reasoner_history_drives_alternate_target_on_recovery():
    class RecoveryExecutor:
        def __init__(self):
            self.actions = []

        def execute(self, action):
            self.actions.append(action)
            return ExecutionResult(accepted=True, changed=True)

    class RecoveryObserver:
        def __init__(self):
            self.calls = 0

        def observe(self):
            self.calls += 1
            return __import__("nova_core.models", fromlist=["Observation"]).Observation(
                "pkg",
                "MainActivity",
                (
                    __import__("nova_core.models", fromlist=["UiElement"]).UiElement("first", text="Continue", clickable=True),
                    __import__("nova_core.models", fromlist=["UiElement"]).UiElement("second", text="Continue", clickable=True),
                ),
                self.calls,
            )

        def observe_fresh(self, previous):
            return self.observe()

    observer = RecoveryObserver()
    executor = RecoveryExecutor()
    runtime = Runtime(
        Goal("Continue"),
        observer,
        DeterministicReasoner(),
        executor,
        lambda goal, before, decision, result, after: len(executor.actions) == 2,
        max_steps=2,
    )

    result = runtime.run()

    assert result.status is RunStatus.SUCCEEDED
    assert [action.target_id for action in executor.actions] == ["first", "second"]
