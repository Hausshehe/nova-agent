from nova_core.learning_memory import LearningMemory, MissionLearningRecord
from nova_core.learning_policy import LearningApplicationPolicy


def _record(goal: str, target: str = "Continue") -> MissionLearningRecord:
    return MissionLearningRecord(
        goal=goal,
        status="failed",
        steps=2,
        ineffective_actions=(
            {"action": "tap", "target": target, "accepted": True, "changed": False},
        ),
    )


def test_reusable_lesson_requires_repeated_evidence():
    memory = LearningMemory(entries=(_record("finish multi step test"),))
    assert memory.extract_lessons("finish multi step test") == ()

    memory = memory.remember(_record("finish multi step test"))
    lessons = memory.extract_lessons("finish multi step test")

    assert len(lessons) == 1
    assert lessons[0].action == "tap"
    assert lessons[0].target == "Continue"
    assert lessons[0].occurrences == 2
    assert lessons[0].confidence == "medium"


def test_lessons_generalize_only_over_shared_goal_tokens():
    memory = LearningMemory(
        entries=(
            _record("finish multi step test"),
            _record("finish multi step test"),
            _record("open settings"),
            _record("open settings"),
        )
    )

    lessons = memory.extract_lessons("finish multi step test now")

    assert len(lessons) == 1
    assert lessons[0].trigger_tokens
    assert "multi" in lessons[0].trigger_tokens
    assert "step" in lessons[0].trigger_tokens


def test_learning_policy_exposes_lessons_as_guidance():
    records = (_record("finish multi step test"), _record("finish multi step test"))
    assessment = LearningApplicationPolicy().assess(records, goal="finish multi step test")

    assert len(assessment.lessons) == 1
    assert any("historically ineffective" in item for item in assessment.guidance)
    assert assessment.relevant == records
