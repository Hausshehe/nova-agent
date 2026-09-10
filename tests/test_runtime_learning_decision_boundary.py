from nova_core.learning_memory import LearningMemory, MissionLearningRecord
from nova_core.models import Action, ActionType, Decision, Goal, Observation, UiElement
from nova_core.planning import Plan, PlanStep
from nova_core.runtime import Runtime
from nova_core.state_machine import RunState


class _Observer:
    def observe(self):
        raise AssertionError("observer should not be called")


class _Executor:
    def execute(self, action):
        raise AssertionError("executor should not be called")


class _Verifier:
    def verify(self, *args):
        raise AssertionError("verifier should not be called")


class _Planner:
    def plan(self, context):
        return Plan((PlanStep("Open settings"),))

    def replan(self, context, previous):
        return Plan((PlanStep("Open settings differently"),), revision=previous.revision + 1)


class _Reasoner:
    def __init__(self):
        self.context = None

    def decide(self, context):
        self.context = context
        return Decision(
            Action(ActionType.TAP, target_id="settings"),
            reason="use current settings target",
            target_label="Settings",
        )


def test_runtime_decision_boundary_receives_learning_assessment() -> None:
    memory = LearningMemory().remember(
        MissionLearningRecord(
            "Open settings",
            "failed",
            2,
            error="target unavailable",
            ineffective_actions=(
                {"action": "tap", "target": "settings"},
            ),
        )
    )
    reasoner = _Reasoner()
    runtime = Runtime(
        Goal("Open settings"),
        _Observer(),
        reasoner,
        _Executor(),
        _Verifier(),
        planner=_Planner(),
        learning_memory=memory,
    )

    runtime.brain.start()
    observation = Observation(
        "pkg",
        "activity",
        (UiElement(id="settings", text="Settings", clickable=True),),
        1,
    )
    runtime.brain.record_observation(observation)
    runtime.evidence.observe(observation)
    runtime.brain.set_plan(Plan((PlanStep("Open settings"),)))

    state = runtime.step()

    assert state is RunState.EXECUTING
    assert reasoner.context is not None
    assert reasoner.context.relevant_learning == memory.retrieve("Open settings")
    assert reasoner.context.learning_assessment is not None
    assert reasoner.context.learning_assessment.warnings == (
        "Historical mission failed: Open settings (target unavailable)",
        "Historical action made no observable progress: tap settings",
    )
    assert reasoner.context.learning_assessment.guidance
