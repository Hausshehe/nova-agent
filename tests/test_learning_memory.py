from nova_core.learning_memory import LearningMemory, MissionLearningRecord
from nova_core.mission_state import MissionState
from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, RunResult, RunStatus


def test_learning_record_preserves_verified_mission_facts() -> None:
    mission = MissionState(Goal("Finish the task")).decided(
        Decision(Action(ActionType.TAP, target_id="next"), target_label="Next")
    ).executed(ExecutionResult(accepted=True, changed=True))
    result = RunResult(RunStatus.SUCCEEDED, steps=1)

    record = MissionLearningRecord.from_mission(mission, result)

    assert record.snapshot() == {
        "goal": "Finish the task",
        "status": "succeeded",
        "steps": 1,
        "error": None,
        "changed_actions": 1,
        "failed_actions": 0,
        "ineffective_actions": [],
    }


def test_learning_record_keeps_ineffective_attempts_as_facts() -> None:
    mission = MissionState(Goal("Recover")).decided(
        Decision(Action(ActionType.TAP, target_id="primary"), target_label="Primary")
    ).executed(ExecutionResult(accepted=True, changed=False))
    result = RunResult(RunStatus.FAILED, steps=0, error="stalled")

    record = MissionLearningRecord.from_mission(mission, result)

    assert record.ineffective_actions == ({
        "action": "tap",
        "target_id": "primary",
        "target_label": "Primary",
        "accepted": True,
        "changed": False,
        "error": None,
    },)


def test_learning_memory_is_bounded_and_keeps_newest_records() -> None:
    memory = LearningMemory(max_entries=2)
    records = [
        MissionLearningRecord(f"goal-{index}", "succeeded", index)
        for index in range(3)
    ]

    memory = memory.remember(records[0]).remember(records[1]).remember(records[2])

    assert memory.entries == (records[1], records[2])
    assert [item["goal"] for item in memory.snapshot()] == ["goal-1", "goal-2"]


def test_learning_memory_rejects_invalid_capacity_or_overflow() -> None:
    try:
        LearningMemory(max_entries=0)
        raise AssertionError("expected invalid capacity to fail")
    except ValueError as exc:
        assert str(exc) == "max_entries must be at least 1"

    record = MissionLearningRecord("goal", "failed", 1)
    try:
        LearningMemory(max_entries=1, entries=(record, record))
        raise AssertionError("expected overflow to fail")
    except ValueError as exc:
        assert str(exc) == "entries exceed max_entries"
