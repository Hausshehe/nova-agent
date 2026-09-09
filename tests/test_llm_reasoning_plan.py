import json

from nova_core.models import Goal, Observation, UiElement
from nova_core.reasoning import ReasoningContext
from nova_core.reasoning_adapter import LLMReasoner


def test_llm_reasoner_prompt_makes_current_plan_intent_explicit():
    prompts = []

    def responder(prompt: str):
        prompts.append(prompt)
        return {
            "action_type": "tap",
            "target_id": "finish",
            "reason": "Tap FINISH to complete the mission.",
        }

    context = ReasoningContext(
        goal=Goal("Finish the multi-step test"),
        observation=Observation(
            package="com.example.app",
            activity="MainActivity",
            revision=4,
            elements=(
                UiElement(id="continue", text="CONTINUE", clickable=True),
                UiElement(id="finish", text="FINISH", clickable=True),
            ),
        ),
    )

    from nova_core.planning import Plan, PlanStep

    context = ReasoningContext(
        goal=context.goal,
        observation=context.observation,
        plan=Plan((PlanStep("finish the test"),), revision=0),
    )

    decision = LLMReasoner(responder).decide(context)
    payload = json.loads(prompts[0])

    assert decision.action.target_id == "finish"
    assert payload["plan"]["current"] == "finish the test"
    assert "The plan's current intent is the immediate mission objective for this decision." in payload["rules"]
    assert "Choose the current UI element that best advances that intent, not a later plan step." in payload["rules"]
    assert "Your reason must describe the actual selected target/action" in payload["rules"]
