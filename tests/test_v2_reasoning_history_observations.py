import json

from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, UiElement
from nova_core.reasoning import ReasoningContext, ReasoningStep
from nova_core.reasoning_adapter import LLMReasoner


def test_llm_reasoner_serializes_post_action_observation_compactly():
    before = Observation(
        package="com.example",
        activity="MainActivity",
        elements=(UiElement("continue", text="Continue Multi-Step", clickable=True),),
        revision=1,
    )
    after = Observation(
        package="com.example",
        activity="MainActivity",
        elements=(UiElement("status", text="Step 2 started"),),
        revision=2,
    )
    history = (
        ReasoningStep(
            decision=Decision(
                Action(ActionType.TAP, target_id="continue"),
                reason="advance the workflow",
                target_label="Continue Multi-Step",
            ),
            execution=ExecutionResult(accepted=True, changed=True),
            post_observation=after,
        ),
    )
    context = ReasoningContext(Goal("Finish Multi-Step Test"), before, history)
    received = []

    def responder(prompt):
        received.append(json.loads(prompt))
        return {
            "action_type": "back",
            "target_id": None,
            "value": None,
            "reason": "test decision",
        }

    LLMReasoner(responder).decide(context)

    payload = received[0]
    assert payload["reasoning_guidance"]
    post_observation = payload["history"][0]["post_observation"]
    assert post_observation["revision"] == 2
    assert post_observation["visible_text"] == ["Step 2 started"]
    assert post_observation["elements"] == [
        {"text": "Step 2 started", "content_description": None}
    ]
