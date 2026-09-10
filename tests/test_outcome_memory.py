from nova_core.mission_state import MissionState
from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal
from nova_core.outcome_memory import ActionOutcome, OutcomeMemory


def test_outcome_memory_is_bounded_and_immutable():
    memory = OutcomeMemory(max_entries=2)
    first = ActionOutcome(ActionType.TAP, "a", "A", True, False)
    second = ActionOutcome(ActionType.TAP, "b", "B", True, True)
    third = ActionOutcome(ActionType.BACK, None, "", True, True)

    updated = memory.remember(first).remember(second).remember(third)

    assert memory.entries == ()
    assert [item.target_id for item in updated.entries] == ["b", None]


def test_ineffective_attempts_are_factual_and_target_scoped():
    memory = OutcomeMemory().remember(ActionOutcome(ActionType.TAP, "a", "A", True, False))
    memory = memory.remember(ActionOutcome(ActionType.TAP, "b", "B", True, False))
    memory = memory.remember(ActionOutcome(ActionType.TAP, "a", "A", True, True))

    assert memory.ineffective_attempts() == 2
    assert memory.ineffective_attempts(target_id="a") == 1
    assert memory.ineffective_attempts(target_id="b") == 1


def test_mission_state_records_action_outcome_for_reasoning():
    decision = Decision(Action(ActionType.TAP, target_id="next"), reason="advance", target_label="Next")
    state = MissionState(Goal("Finish")).decided(decision).executed(
        ExecutionResult(accepted=True, changed=False, error=None)
    )

    assert len(state.outcome_memory.entries) == 1
    outcome = state.outcome_memory.entries[0]
    assert outcome.action_type is ActionType.TAP
    assert outcome.target_id == "next"
    assert outcome.target_label == "Next"
    assert outcome.accepted is True
    assert outcome.changed is False
    assert state.reasoning_snapshot()["recent_action_outcomes"] == [
        {
            "action": "tap",
            "target_id": "next",
            "target_label": "Next",
            "accepted": True,
            "changed": False,
            "error": None,
        }
    ]


def test_failed_outcome_preserves_error_for_reasoning():
    decision = Decision(Action(ActionType.TAP, target_id="blocked"), target_label="Blocked")
    state = MissionState(Goal("Recover")).decided(decision).executed(
        ExecutionResult(accepted=False, changed=False, error="disabled")
    )

    assert state.reasoning_snapshot()["recent_action_outcomes"][0]["error"] == "disabled"
