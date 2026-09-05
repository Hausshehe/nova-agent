from nova_core.adapters.android import AndroidBridgeAdapter
from nova_core.models import Observation


class FakeState:
    def __init__(self, elements):
        self.package = "pkg"
        self.activity = "MainActivity"
        self.elements = elements


class FakeBridge:
    def __init__(self):
        self.calls = 0

    def observe(self):
        self.calls += 1
        return FakeState([] if self.calls == 1 else [object()])


def test_initial_observation_polls_until_ui_tree_is_available():
    bridge = FakeBridge()
    adapter = AndroidBridgeAdapter(bridge)

    observation = adapter.observe()

    assert isinstance(observation, Observation)
    assert len(observation.elements) == 1
    assert bridge.calls == 2
