from agent.core import ActionType, ExecutionResult, UIElement, WorldState
from agent.llm_reasoning_provider import LLMReasoningProvider
from agent.navigation import NavigationLoop


class RecoveryBridge:
    def __init__(self):
        self.states = [
            WorldState(
                package="nova",
                activity="MainActivity",
                observation_id="before",
                elements=(UIElement("wrong", text="Wrong Action", clickable=True),),
            ),
            WorldState(
                package="nova",
                activity="MainActivity",
                observation_id="after-failure",
                elements=(UIElement("retry", text="Retry", clickable=True),),
            ),
            WorldState(
                package="nova",
                activity="MainActivity",
                observation_id="done",
                elements=(UIElement("done", text="Recovery Completed", clickable=False),),
            ),
        ]
        self.index = 0
        self.executed = []

    def observe(self):
        return self.states[self.index]

    def execute(self, action):
        self.executed.append(action)
        if action.target.element_id == "wrong":
            return ExecutionResult(accepted=False, changed=False, error="rejected")
        self.index = 2
        return ExecutionResult(accepted=True, changed=True)

    def wait_for_fresh_observation(self, previous, timeout):
        assert timeout == 2.0
        if previous.observation_id == "before":
            self.index = 1
        return self.states[self.index]


def test_llm_provider_reasons_again_after_failed_action_and_reaches_goal():
    bridge = RecoveryBridge()
    prompts = []

    def responder(prompt):
        prompts.append(prompt)
        if len(prompts) == 1:
            return {
                "action_type": "click",
                "target": {"element_id": "wrong"},
                "reason": "first attempt",
            }
        return {
            "action_type": "click",
            "target": {"element_id": "retry"},
            "reason": "retry after the failed attempt",
        }

    provider = LLMReasoningProvider(responder)
    achieved = NavigationLoop(bridge=bridge, planner=provider, max_steps=2).run(
        "Recovery completed"
    )

    assert achieved is True
    assert len(prompts) == 2
    assert '"observation_id":"after-failure"' in prompts[1]
    assert '"target_id":"wrong"' in prompts[1]
    assert '"accepted":false' in prompts[1]
    assert len(bridge.executed) == 2
    assert all(action.type is ActionType.CLICK for action in bridge.executed)
    assert bridge.executed[1].target.element_id == "retry"
