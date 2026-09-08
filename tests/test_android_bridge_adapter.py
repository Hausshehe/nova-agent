from nova_core.adapters.android import AndroidBridgeAdapter
from nova_core.models import Action, ActionType, Observation, ExecutionResult


class FakeState:
    def __init__(self, elements, package="pkg", observation_id=""):
        self.package = package
        self.activity = "MainActivity"
        self.elements = elements
        self.observation_id = observation_id


class FakeElement:
    id = "button"
    text = "Button"
    content_description = ""
    clickable = True
    enabled = True
    class_name = "Button"
    editable = False
    scrollable = False
    checkable = False
    checked = False
    focused = False
    visible = True


class FakeStatusElement:
    id = "status"
    content_description = ""
    clickable = False
    enabled = True
    class_name = "TextView"
    editable = False
    scrollable = False
    checkable = False
    checked = False
    focused = False
    visible = True

    def __init__(self, text):
        self.text = text


class FakeBridge:
    def __init__(self):
        self.calls = 0

    def observe(self):
        self.calls += 1
        return FakeState([] if self.calls == 1 else [FakeElement()])


class FakeLaunchBridge:
    def __init__(self):
        self.calls = 0

    def observe(self):
        self.calls += 1
        if self.calls == 1:
            return FakeState([FakeElement()], package="com.termux")
        return FakeState([FakeElement()], package="com.hausshehe.nova")


class FakeFreshBridge:
    def __init__(self):
        self.calls = 0

    def observe(self):
        self.calls += 1
        if self.calls == 1:
            return FakeState([FakeStatusElement("Step 2 started")], observation_id="1")
        if self.calls == 2:
            return FakeState([FakeStatusElement("Multi-Step Test completed")], observation_id="2")
        return FakeState([FakeStatusElement("Multi-Step Test completed")], observation_id=str(self.calls))

    def wait_for_fresh_observation(self, previous, timeout=2.0, poll_seconds=0.2):
        return self.observe()


def test_initial_observation_polls_until_ui_tree_is_available():
    bridge = FakeBridge()
    adapter = AndroidBridgeAdapter(bridge)

    observation = adapter.observe()

    assert isinstance(observation, Observation)
    assert len(observation.elements) == 1
    assert bridge.calls == 2


def test_initial_observation_ignores_non_expected_package():
    bridge = FakeLaunchBridge()
    adapter = AndroidBridgeAdapter(bridge, expected_package="com.hausshehe.nova")

    observation = adapter.observe()

    assert observation.package == "com.hausshehe.nova"
    assert bridge.calls == 2


def test_observe_fresh_waits_for_a_stable_ui_state():
    bridge = FakeFreshBridge()
    adapter = AndroidBridgeAdapter(bridge)
    initial = adapter.observe()

    # Replace the initial legacy state with the state that a real execution
    # would have immediately before waiting for the post-action transition.
    adapter._last_legacy_state = FakeState(
        [FakeStatusElement("Step 1 started")], observation_id="0"
    )
    adapter._revision = initial.revision

    observation = adapter.observe_fresh(initial)

    assert observation.elements[0].text == "Multi-Step Test completed"
    assert observation.revision == initial.revision + 1
