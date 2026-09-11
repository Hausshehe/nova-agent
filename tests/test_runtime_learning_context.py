from __future__ import annotations

import json

from nova_core.learning_memory import LearningMemory, MissionLearningRecord
from nova_core.learning_policy import LearningApplicationPolicy
from nova_core.models import Action, ActionType, Decision, Goal, Observation, UiElement
from nova_core.reasoning_adapter import LLMReasoner
from nova_core.runtime import Runtime


class _Observer:
    def observe(self):
        raise AssertionError("observer should not be called")


class _Reasoner:
    def decide(self, context):
        self.context = context
        raise AssertionError("reasoner should not be called")


class _Executor:
    def execute(self, action):
        raise AssertionError("executor should not be called")


class _Verifier:
    def verify(self, *args):
        raise AssertionError("verifier should not be called")


def test_runtime_reasoning_context_applies_learning_policy() -> None:
    memory = LearningMemory().remember(
        MissionLearningRecord(
            "Open settings",
            "failed",
            2,
            error="target unavailable",
            ineffective_actions=(
                {"action": "tap", "target": "settings_button"},
            ),
        )
    )
    runtime = Runtime(
        Goal("Open settings"),
        _Observer(),
        _Reasoner(),
        _Executor(),
        _Verifier(),
        learning_memory=memory,
    )
    runtime.brain.start()
    observation = Observation("pkg", "activity", (), 1)
    runtime.brain.record_observation(observation)
    runtime.evidence.observe(observation)

    context = runtime._reasoning_context()

    assert context.relevant_learning == memory.retrieve("Open settings")
    assert context.learning_assessment is not None
    assert context.learning_assessment.warnings == (
        "Historical mission failed: Open settings (target unavailable)",
        "Historical action made no observable progress: tap settings_button",
    )


def test_runtime_accepts_injected_learning_policy() -> None:
    class RecordingPolicy(LearningApplicationPolicy):
        def __init__(self):
            self.calls = []

        def assess(self, records):
            self.calls.append(records)
            return super().assess(records)

    policy = RecordingPolicy()
    memory = LearningMemory().remember(
        MissionLearningRecord("Open settings", "succeeded", 1)
    )
    runtime = Runtime(
        Goal("Open settings"),
        _Observer(),
        _Reasoner(),
        _Executor(),
        _Verifier(),
        learning_memory=memory,
        learning_policy=policy,
    )
    runtime.brain.start()
    observation = Observation("pkg", "activity", (), 1)
    runtime.brain.record_observation(observation)
    runtime.evidence.observe(observation)

    runtime._reasoning_context()

    assert policy.calls == [memory.retrieve("Open settings")]


def test_runtime_reasoning_context_includes_reusable_ineffective_lesson() -> None:
    record = MissionLearningRecord(
        "Open settings quickly",
        "failed",
        2,
        ineffective_actions=(
            {"action": "tap", "target": "settings_button"},
        ),
    )
    memory = LearningMemory(entries=(record, record))
    runtime = Runtime(
        Goal("Open settings quickly"),
        _Observer(),
        _Reasoner(),
        _Executor(),
        _Verifier(),
        learning_memory=memory,
    )
    runtime.brain.start()
    observation = Observation("pkg", "activity", (), 1)
    runtime.brain.record_observation(observation)
    runtime.evidence.observe(observation)

    context = runtime._reasoning_context()

    assert context.learning_assessment is not None
    assert len(context.learning_assessment.lessons) == 1
    lesson = context.learning_assessment.lessons[0]
    assert lesson.action == "tap"
    assert lesson.target == "settings_button"
    assert lesson.occurrences == 2
    assert lesson.confidence == "medium"
    assert "historically ineffective" in context.learning_assessment.guidance[-1]


def test_runtime_learning_does_not_create_lesson_from_single_failure() -> None:
    memory = LearningMemory().remember(
        MissionLearningRecord(
            "Open settings",
            "failed",
            1,
            ineffective_actions=(
                {"action": "tap", "target": "settings_button"},
            ),
        )
    )
    runtime = Runtime(
        Goal("Open settings"),
        _Observer(),
        _Reasoner(),
        _Executor(),
        _Verifier(),
        learning_memory=memory,
    )
    runtime.brain.start()
    observation = Observation("pkg", "activity", (), 1)
    runtime.brain.record_observation(observation)
    runtime.evidence.observe(observation)

    context = runtime._reasoning_context()

    assert context.learning_assessment is not None
    assert context.learning_assessment.lessons == ()


def test_experience_can_change_llm_decision_toward_current_alternative() -> None:
    record = MissionLearningRecord(
        "Open settings quickly",
        "failed",
        2,
        ineffective_actions=(
            {"action": "tap", "target": "settings_button"},
        ),
    )
    memory = LearningMemory(entries=(record, record))
    runtime = Runtime(
        Goal("Open settings quickly"),
        _Observer(),
        _Reasoner(),
        _Executor(),
        _Verifier(),
        learning_memory=memory,
    )
    runtime.brain.start()
    observation = Observation(
        "pkg",
        "activity",
        (
            UiElement("settings_button", text="Settings", clickable=True),
            UiElement("preferences_button", text="Preferences", clickable=True),
        ),
        2,
    )
    runtime.brain.record_observation(observation)
    runtime.evidence.observe(observation)
    context = runtime._reasoning_context()

    seen = {}

    def responder(prompt: str):
        payload = json.loads(prompt)
        seen["learning"] = payload["learning"]
        seen["observation"] = payload["observation"]
        return {
            "action_type": "tap",
            "target_id": "preferences_button",
            "reason": "The historical settings target was ineffective; the current alternative is available.",
        }

    decision = LLMReasoner(responder).decide(context)

    assert seen["learning"]["assessment"]["guidance"]
    assert any("historically ineffective" in item for item in seen["learning"]["assessment"]["guidance"])
    assert {item["id"] for item in seen["observation"]["actions"]} == {
        "settings_button",
        "preferences_button",
    }
    assert decision.action == Action(ActionType.TAP, target_id="preferences_button")


def test_experience_warning_does_not_override_current_evidence() -> None:
    record = MissionLearningRecord(
        "Open settings",
        "failed",
        2,
        ineffective_actions=(
            {"action": "tap", "target": "settings_button"},
        ),
    )
    memory = LearningMemory(entries=(record, record))
    runtime = Runtime(
        Goal("Open settings"),
        _Observer(),
        _Reasoner(),
        _Executor(),
        _Verifier(),
        learning_memory=memory,
    )
    runtime.brain.start()
    observation = Observation(
        "pkg",
        "activity",
        (UiElement("settings_button", text="Settings", clickable=True),),
        3,
    )
    runtime.brain.record_observation(observation)
    runtime.evidence.observe(observation)
    context = runtime._reasoning_context()

    def responder(prompt: str):
        payload = json.loads(prompt)
        assert any("historically ineffective" in item for item in payload["learning"]["assessment"]["guidance"])
        assert payload["observation"]["actions"][0]["id"] == "settings_button"
        return {
            "action_type": "tap",
            "target_id": "settings_button",
            "reason": "Current UI evidence makes the target available now.",
        }

    decision = LLMReasoner(responder).decide(context)

    assert decision.action == Action(ActionType.TAP, target_id="settings_button")
