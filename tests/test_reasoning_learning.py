import json

from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, UiElement
from nova_core.reasoning import ReasoningContext, ReasoningStep
from nova_core.reasoning_adapter import LLMReasoner


def _context(history=()):
    observation = Observation(
        package="com.example",
        activity="MainActivity",
        elements=(UiElement(id="continue", text="CONTINUE", clickable=True),),
        revision=3,
    )
    return ReasoningContext(goal=Goal("Finish task"), observation=observation, history=history)


def _step(target="continue", changed=False):
    return ReasoningStep(
        decision=Decision(Action(ActionType.TAP, target_id=target), "try it", "CONTINUE"),
        execution=ExecutionResult(accepted=True, changed=changed),
        post_observation=Observation("com.example", "MainActivity", (), 3),
    )


def _capture(context):
    captured = {}

    def responder(prompt):
        captured.update(json.loads(prompt))
        return {"action_type": "tap", "target_id": "continue", "reason": "test"}

    LLMReasoner(responder).decide(context)
    return captured


def test_reasoning_exposes_accepted_action_with_no_progress():
    payload = _capture(_context((_step(changed=False),)))

    assert payload["learning"]["accepted_but_no_progress"] == [
        {"action": "tap", "target": "continue", "label": "CONTINUE"}
    ]
    assert payload["learning"]["repeated_ineffective_actions"] == []


def test_reasoning_counts_repeated_ineffective_action_by_target():
    payload = _capture(_context((_step(changed=False), _step(changed=False))))

    assert payload["learning"]["repeated_ineffective_actions"] == [
        {"action": "tap", "target": "continue", "attempts": 2}
    ]


def test_successful_action_is_not_marked_ineffective():
    payload = _capture(_context((_step(changed=True),)))

    assert payload["learning"]["accepted_but_no_progress"] == []
    assert payload["learning"]["repeated_ineffective_actions"] == []
