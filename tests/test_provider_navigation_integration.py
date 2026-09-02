from agent.core import ActionType, ExecutionResult, UIElement, WorldState
from agent.navigation import NavigationLoop
from agent.structured_reasoning_provider import StructuredReasoningProvider


class FakeBridge:
    def __init__(self):
        self.states = [
            WorldState(
                package="nova",
                activity="MainActivity",
                observation_id="before",
                elements=(UIElement("n1", text="Continue", clickable=True),),
            ),
            WorldState(
                package="nova",
                activity="MainActivity",
                observation_id="after",
                elements=(UIElement("n2", text="Done", clickable=True),),
            ),
        ]
        self.executed = []

    def observe(self):
        return self.states[0]

    def execute(self, action):
        self.executed.append(action)
        return ExecutionResult(accepted=True, changed=True)

    def wait_for_fresh_observation(self, previous, timeout):
        assert previous.observation_id == "before"
        assert timeout == 2.0
        return self.states[1]


def test_structured_provider_runs_through_navigation_loop():
    bridge = FakeBridge()
    received = []

    def responder(payload):
        received.append(payload)
        assert payload["goal"] == "Tap Continue"
        assert payload["state"]["observation_id"] == "before"
        assert payload["candidates"][0]["target"]["element_id"] == "n1"
        return {
            "action_type": "click",
            "target": {"element_id": "n1"},
            "reason": "structured provider selected the visible goal target",
        }

    provider = StructuredReasoningProvider(responder)
    achieved = NavigationLoop(
        bridge=bridge,
        planner=provider,
        max_steps=1,
    ).run("Tap Continue")

    assert achieved is True
    assert len(received) == 1
    assert len(bridge.executed) == 1
    assert bridge.executed[0].type is ActionType.CLICK
    assert bridge.executed[0].target.element_id == "n1"
