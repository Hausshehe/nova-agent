import json

from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, UiElement
from nova_core.reasoning import ReasoningContext, ReasoningStep
from nova_core.reasoning_adapter import LLMReasoner


def _context() -> ReasoningContext:
    observation = Observation(
        package="com.hausshehe.nova",
        activity="MainActivity",
        revision=2,
        elements=(
            UiElement("failed", text="Blocked action", clickable=True),
            UiElement("alternative", text="Continue", clickable=True),
        ),
    )
    step = ReasoningStep(
        decision=Decision(Action(ActionType.TAP, target_id="failed"), target_label="Blocked action"),
        execution=ExecutionResult(accepted=True, changed=False, error="no state change"),
        post_observation=observation,
    )
    return ReasoningContext(goal=Goal("Continue"), observation=observation, history=(step,))


def test_recovery_context_marks_failed_strategy_and_exposes_current_alternative():
    prompts = []

    def responder(prompt):
        prompts.append(json.loads(prompt))
        return {"action_type": "tap", "target_id": "alternative", "reason": "use the visible alternative"}

    decision = LLMReasoner(responder).decide(_context())

    recovery = prompts[0]["recovery"]
    assert recovery["active"] is True
    assert recovery["ineffective_recent_actions"] == [{
        "action": "tap",
        "target": "failed",
        "label": "Blocked action",
        "error": "no state change",
    }]
    assert {item["target"] for item in recovery["available_alternatives"]} == {"alternative"}
    assert decision.action.target_id == "alternative"


def test_recovery_context_does_not_activate_without_ineffective_history():
    observation = Observation(
        package="nova",
        activity="MainActivity",
        revision=1,
        elements=(UiElement("continue", text="Continue", clickable=True),),
    )
    context = ReasoningContext(goal=Goal("Continue"), observation=observation)
    payloads = []

    def responder(prompt):
        payloads.append(json.loads(prompt))
        return {"action_type": "tap", "target_id": "continue", "reason": "advance"}

    LLMReasoner(responder).decide(context)

    assert payloads[0]["recovery"] == {"active": False}
