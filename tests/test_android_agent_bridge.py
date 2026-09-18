from agent.android_bridge import AndroidBridge


class FakeBridge(AndroidBridge):
    def __init__(self):
        super().__init__()
        self.payloads = []

    def _request(self, payload):
        self.payloads.append(payload)
        return {"ok": True, "accepted": True}


def test_start_agent_sends_goal_and_deadline():
    bridge = FakeBridge()

    result = bridge.start_agent("Tap the button", 123456)

    assert result["accepted"] is True
    assert bridge.payloads == [{
        "command": "agent_goal",
        "goal": "Tap the button",
        "deadlineMs": 123456,
    }]


def test_agent_status_and_cancel_use_runtime_commands():
    bridge = FakeBridge()

    bridge.agent_status()
    bridge.cancel_agent()

    assert bridge.payloads == [
        {"command": "agent_status"},
        {"command": "agent_cancel"},
    ]


def test_start_agent_rejects_blank_goal_and_negative_deadline():
    bridge = FakeBridge()

    try:
        bridge.start_agent("   ")
    except ValueError as exc:
        assert "blank" in str(exc)
    else:
        raise AssertionError("blank goal should fail")

    try:
        bridge.start_agent("do it", -1)
    except ValueError as exc:
        assert "negative" in str(exc)
    else:
        raise AssertionError("negative deadline should fail")
