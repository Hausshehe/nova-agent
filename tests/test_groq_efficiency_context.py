import json

from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, UiElement
from nova_core.reasoning import ReasoningContext, ReasoningStep
from nova_core.reasoning_adapter import _reasoning_payload


def _context(history: tuple[ReasoningStep, ...]) -> ReasoningContext:
    observation = Observation(
        package="com.hausshehe.nova",
        activity="MainActivity",
        revision=3,
        elements=(
            UiElement(id="multi_step_test", text="MULTI-STEP TEST", clickable=True),
            UiElement(id="continue_multi_step", text="CONTINUE MULTI-STEP", clickable=True),
        ),
    )
    return ReasoningContext(goal=Goal("Finish Multi-Step Test"), observation=observation, history=history)


def _step(*, changed: bool, target: str = "multi_step_test") -> ReasoningStep:
    return ReasoningStep(
        decision=Decision(Action(ActionType.TAP, target_id=target), target_label="MULTI-STEP TEST"),
        execution=ExecutionResult(accepted=True, changed=changed),
        post_observation=Observation(
            package="com.hausshehe.nova",
            activity="MainActivity",
            revision=4,
            elements=(UiElement(id="continue_multi_step", text="CONTINUE MULTI-STEP", clickable=True),),
        ),
    )


def test_successful_history_is_not_repeated_in_reasoning_prompt():
    payload = _reasoning_payload(_context((_step(changed=True),)))

    assert payload["history"] == []
    assert payload["mission"]["last_action"] == "tap"
    assert payload["mission"]["last_execution"] == {"accepted": True, "changed": True, "error": None}


def test_failed_or_stalled_history_remains_available_for_recovery():
    payload = _reasoning_payload(_context((_step(changed=False),)))

    assert len(payload["history"]) == 1
    assert payload["history"][0]["changed"] is False
    assert payload["recovery"]["active"] is True


def test_successful_history_compaction_reduces_serialized_context():
    successful = _context(tuple(_step(changed=True) for _ in range(3)))
    stalled = _context(tuple(_step(changed=False) for _ in range(3)))

    compact_size = len(json.dumps(_reasoning_payload(successful), separators=(",", ":")))
    recovery_size = len(json.dumps(_reasoning_payload(stalled), separators=(",", ":")))

    assert compact_size < recovery_size
