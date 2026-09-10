from __future__ import annotations

import pytest

from nova_core.learning_memory import MissionLearningRecord
from nova_core.learning_policy import LearningApplicationPolicy


def test_policy_keeps_history_as_evidence_and_warns_about_failures() -> None:
    records = (
        MissionLearningRecord(
            "Open settings",
            "failed",
            2,
            error="target unavailable",
            failed_actions=1,
            ineffective_actions=(
                {"action": "tap", "target": "settings_button"},
            ),
        ),
        MissionLearningRecord("Open camera", "succeeded", 1),
    )

    assessment = LearningApplicationPolicy().assess(records)

    assert assessment.relevant == records
    assert assessment.warnings == (
        "Historical mission failed: Open settings (target unavailable)",
        "Historical action made no observable progress: tap settings_button",
        "Historical mission had 1 rejected action(s): Open settings",
    )
    assert "current observation has priority" in assessment.guidance[1]


def test_policy_does_not_turn_success_into_authorization() -> None:
    record = MissionLearningRecord("Open settings", "succeeded", 1)

    assessment = LearningApplicationPolicy().assess((record,))

    assert assessment.warnings == ()
    assert any("never authorizes an action" in item for item in assessment.guidance)


def test_policy_bounds_records_and_warnings() -> None:
    records = tuple(
        MissionLearningRecord(
            f"Goal {index}",
            "failed",
            1,
            error="failed",
            ineffective_actions=(
                {"action": "tap", "target": f"target-{index}"},
                {"action": "tap", "target": f"target-{index}-2"},
                {"action": "tap", "target": f"target-{index}-3"},
            ),
            failed_actions=1,
        )
        for index in range(10)
    )

    assessment = LearningApplicationPolicy().assess(records)

    assert len(assessment.relevant) == 4
    assert len(assessment.warnings) == 8


def test_policy_rejects_non_tuple_or_invalid_records() -> None:
    policy = LearningApplicationPolicy()

    with pytest.raises(TypeError):
        policy.assess([])  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        policy.assess(("not a record",))  # type: ignore[arg-type]
