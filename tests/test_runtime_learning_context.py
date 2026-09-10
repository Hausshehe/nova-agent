from __future__ import annotations

from nova_core.learning_memory import LearningMemory, MissionLearningRecord
from nova_core.learning_policy import LearningApplicationPolicy
from nova_core.models import Goal
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
    # Install the minimum current observation required by RuntimeBrain without
    # exercising the Android observer or the mission lifecycle.
    from nova_core.models import Observation
    runtime.brain.record_observation(Observation("pkg", "activity", 1, ()))

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
    from nova_core.models import Observation
    runtime.brain.record_observation(Observation("pkg", "activity", 1, ()))

    runtime._reasoning_context()

    assert policy.calls == [memory.retrieve("Open settings")]
