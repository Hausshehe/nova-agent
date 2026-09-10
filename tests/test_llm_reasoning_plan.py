import json

from nova_core.mission_state import MissionState
from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, UiElement
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
    assert "Your reason must describe the actual selected target/action." in payload["rules"]


def test_llm_reasoner_prompt_contains_bounded_mission_state():
    prompts = []

    def responder(prompt: str):
        prompts.append(prompt)
        return {
            "action_type": "tap",
            "target_id": "finish",
            "reason": "Tap FINISH because it is the current available target.",
        }

    mission = MissionState(Goal("Finish the test"))
    mission = mission.observed(
        Observation(
            package="com.example.app",
            activity="MainActivity",
            revision=7,
            elements=(UiElement(id="finish", text="FINISH", clickable=True),),
        )
    ).decided(Decision(Action(ActionType.TAP, target_id="finish"), reason="advance", target_label="FINISH"))
    mission = mission.executed(ExecutionResult(accepted=True, changed=True))

    context = ReasoningContext(
        goal=mission.goal,
        observation=mission.observation,
        mission_state=mission,
    )
    LLMReasoner(responder).decide(context)
    payload = json.loads(prompts[0])

    assert payload["mission"]["current_observation_revision"] == 7
    assert payload["mission"]["last_action"] == "tap"
    assert payload["mission"]["last_target_label"] == "FINISH"
    assert payload["mission"]["last_execution"] == {"accepted": True, "changed": True, "error": None}
    assert payload["mission"]["changed_actions"] == 1
    assert "The current observation is authoritative for what is available now." in " ".join(payload["rules"])
