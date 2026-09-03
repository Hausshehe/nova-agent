from agent.core import ExecutionResult as LegacyExecutionResult
from agent.core import UIElement, WorldState
from nova_core.adapters.android import AndroidBridgeAdapter, AndroidGoalVerifier
from nova_core.models import Action, ActionType, ExecutionResult, Goal


class FakeBridge:
    def __init__(self):
        self.executed = []
        self.state = WorldState(
            package="com.example",
            activity="MainActivity",
            observation_id="obs-1",
            elements=(
                UIElement(
                    id="button-1",
                    text="Continue",
                    clickable=True,
                    enabled=True,
                    visible=True,
                ),
            ),
        )
        self.fresh_calls = []

    def observe(self):
        return self.state

    def execute(self, action):
        self.executed.append(action)
        return LegacyExecutionResult(accepted=True, changed=True)

    def wait_for_fresh_observation(self, previous, timeout, poll_seconds):
        self.fresh_calls.append((previous, timeout, poll_seconds))
        return WorldState(
            package=self.state.package,
            activity=self.state.activity,
            observation_id="obs-2",
            elements=self.state.elements,
        )


def test_android_adapter_observe_translates_bridge_state():
    bridge = FakeBridge()
    adapter = AndroidBridgeAdapter(bridge)

    first = adapter.observe()
    second = adapter.observe()

    assert first.package == "com.example"
    assert first.activity == "MainActivity"
    assert first.elements[0].id == "button-1"
    assert first.elements[0].text == "Continue"
    assert first.revision == 1
    assert second.revision == 2


def test_android_adapter_observe_fresh_uses_last_bridge_observation():
    bridge = FakeBridge()
    adapter = AndroidBridgeAdapter(bridge)

    before = adapter.observe()
    after = adapter.observe_fresh(before)

    assert after.revision == 2
    assert bridge.fresh_calls == [(bridge.state, 2.0, 0.2)]
    assert after.package == before.package
    assert after.elements == before.elements


def test_android_adapter_translates_supported_v2_actions():
    bridge = FakeBridge()
    adapter = AndroidBridgeAdapter(bridge)

    assert adapter.execute(Action(ActionType.TAP, target_id="button-1")) == ExecutionResult(True, True)
    assert adapter.execute(Action(ActionType.BACK)) == ExecutionResult(True, True)
    assert adapter.execute(Action(ActionType.SCROLL, target_id="button-1")) == ExecutionResult(True, True)

    assert [action.type.value for action in bridge.executed] == ["click", "back", "scroll"]
    assert bridge.executed[0].target.element_id == "button-1"
    assert bridge.executed[2].target.element_id == "button-1"


def test_android_adapter_rejects_unsupported_v2_action_without_bridge_call():
    bridge = FakeBridge()
    adapter = AndroidBridgeAdapter(bridge)

    result = adapter.execute(Action(ActionType.TYPE, target_id="field", value="hello"))

    assert result.accepted is False
    assert result.changed is False
    assert "unsupported" in result.error
    assert bridge.executed == []


def test_android_goal_verifier_requires_real_transition_and_delegates_goal_semantics():
    calls = []

    def evaluate(goal_text, observation):
        calls.append((goal_text, observation))
        return goal_text == "finish" and observation.elements[0].text == "Finished"

    verifier = AndroidGoalVerifier(evaluate)
    before = AndroidBridgeAdapter(FakeBridge()).observe()
    after = before.__class__(
        package=before.package,
        activity=before.activity,
        elements=(
            before.elements[0].__class__(
                id="button-1",
                text="Finished",
                clickable=True,
                enabled=True,
                visible=True,
            ),
        ),
        revision=before.revision + 1,
    )

    assert verifier.verify(
        Goal("finish"),
        before,
        Action(ActionType.TAP, target_id="button-1"),
        ExecutionResult(True, True),
        after,
    ) is True
    assert calls == [("finish", after)]


def test_android_goal_verifier_rejects_unchanged_or_unaccepted_transition():
    bridge = FakeBridge()
    before = AndroidBridgeAdapter(bridge).observe()
    evaluator = lambda *_: True
    verifier = AndroidGoalVerifier(evaluator)

    assert not verifier.verify(
        Goal("finish"),
        before,
        Action(ActionType.TAP, target_id="button-1"),
        ExecutionResult(True, False),
        before,
    )
    assert not verifier.verify(
        Goal("finish"),
        before,
        Action(ActionType.TAP, target_id="button-1"),
        ExecutionResult(False, True),
        before,
    )
