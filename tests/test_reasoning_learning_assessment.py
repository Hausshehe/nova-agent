from __future__ import annotations

from types import SimpleNamespace

from nova_core.learning_memory import MissionLearningRecord
from nova_core.learning_policy import LearningApplicationPolicy
from nova_core.reasoning_adapter import _learning_payload


def test_reasoning_payload_exposes_policy_assessment_without_bypassing_it() -> None:
    records = (
        MissionLearningRecord(
            "Open settings",
            "failed",
            2,
            error="target unavailable",
            ineffective_actions=(
                {"action": "tap", "target": "settings_button"},
            ),
        ),
    )
    assessment = LearningApplicationPolicy().assess(records)
    context = SimpleNamespace(
        history=(),
        relevant_learning=records,
        learning_assessment=assessment,
    )

    payload = _learning_payload(context)

    assert payload["cross_mission"] == [records[0].snapshot()]
    assert payload["assessment"] == {
        "warnings": [
            "Historical mission failed: Open settings (target unavailable)",
            "Historical action made no observable progress: tap settings_button",
        ],
        "guidance": list(assessment.guidance),
    }


def test_reasoning_payload_keeps_learning_assessment_optional() -> None:
    context = SimpleNamespace(
        history=(),
        relevant_learning=(),
        learning_assessment=None,
    )

    payload = _learning_payload(context)

    assert payload["assessment"] is None
