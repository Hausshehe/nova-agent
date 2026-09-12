from agent.core import WorldState, UIElement
from agent.android_bridge import AndroidBridge


class FakeBridge(AndroidBridge):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def _request(self, payload):
        self.calls += 1
        return {
            "ok": True,
            "state": {
                "observationId": str(self.calls + 1),
                "package": "com.hausshehe.nova",
                "activity": "MainActivity",
                "timestampMs": self.calls,
                "elements": [
                    {
                        "id": "button",
                        "text": "Recovery Primary Action",
                        "clickable": True,
                        "enabled": True,
                    }
                ],
            },
        }


def test_fresh_observation_accepts_new_snapshot_with_unchanged_ui():
    bridge = FakeBridge()
    previous = WorldState(
        observation_id="1",
        package="com.hausshehe.nova",
        activity="MainActivity",
        elements=(
            UIElement(
                id="button",
                text="Recovery Primary Action",
                clickable=True,
                enabled=True,
            ),
        ),
    )

    state = bridge.wait_for_fresh_observation(previous)

    assert state.observation_id == "2"
    assert state.elements == previous.elements
    assert bridge.calls == 1
