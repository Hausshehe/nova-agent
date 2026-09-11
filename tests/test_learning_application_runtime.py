from nova_core.learning_memory import LearningMemory, MissionLearningRecord
from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, RunStatus, UiElement
from nova_core.planning import Plan, PlanStep
from nova_core.reasoning import ReasoningContext
from nova_core.runtime import Runtime


class Observer:
    def __init__(self) -> None:
        self.revision = 0

    def observe(self) -> Observation:
        self.revision += 1
        return Observation(
            package="com.example.app",
            activity="MainActivity",
            revision=self.revision,
            elements=(UiElement(id="continue", text="Continue", clickable=True),),
        )


class Executor:
    def execute(self, action: Action) -> ExecutionResult:
        return ExecutionResult(accepted=True, changed=True)


class Planner:
    def plan(self, context: ReasoningContext) -> Plan:
        return Plan((PlanStep("continue"),))


class SuccessVerifier:
    def verify(self, goal, before, decision, result, after) -> bool:
        return True


class CaptureReasoner:
    def __init__(self) -> None:
        self.context: ReasoningContext | None = None

    def decide(self, context: ReasoningContext) -> Decision:
        self.context = context
        return Decision(Action(ActionType.TAP, target_id="continue"), reason="continue")


def _ineffective_record(goal: str) -> MissionLearningRecord:
    return MissionLearningRecord(
        goal=goal,
        status=RunStatus.SUCCEEDED.value,
        steps=2,
        changed_actions=1,
        ineffective_actions=(
            {"action": ActionType.TAP.value, "target": "continue", "accepted": True, "changed": False},
        ),
    )


def test_runtime_applies_relevant_repeated_lesson_to_current_reasoning() -> None:
    memory = LearningMemory(entries=(
        _ineffective_record("Open settings"),
        _ineffective_record("Open settings"),
    ))
    reasoner = CaptureReasoner()
    runtime = Runtime(Goal("Open settings page"), Observer(), reasoner, Executor(), SuccessVerifier(), max_steps=1, planner=Planner(), learning_memory=memory)
    result = runtime.run()
    assert result.status is RunStatus.SUCCEEDED
    assert reasoner.context is not None
    assessment = reasoner.context.learning_assessment
    assert assessment is not None
    assert len(assessment.lessons) == 1
    assert assessment.lessons[0].action == ActionType.TAP.value
    assert assessment.lessons[0].target == "continue"
    assert assessment.lessons[0].occurrences == 2
    assert "Treat this as a warning, not a prohibition." in assessment.lessons[0].guidance


def test_unrelated_learning_does_not_create_a_current_goal_lesson() -> None:
    memory = LearningMemory(entries=(_ineffective_record("Open camera"), _ineffective_record("Open camera")))
    reasoner = CaptureReasoner()
    runtime = Runtime(Goal("Open settings page"), Observer(), reasoner, Executor(), SuccessVerifier(), max_steps=1, planner=Planner(), learning_memory=memory)
    runtime.run()
    assert reasoner.context is not None
    assert reasoner.context.learning_assessment is not None
    assert reasoner.context.learning_assessment.lessons == ()


def test_retrieved_learning_remains_historical_evidence_in_context() -> None:
    record = MissionLearningRecord("Open settings", "succeeded", 1, changed_actions=1)
    memory = LearningMemory(entries=(record,))
    reasoner = CaptureReasoner()
    runtime = Runtime(Goal("Open settings page"), Observer(), reasoner, Executor(), SuccessVerifier(), max_steps=1, planner=Planner(), learning_memory=memory)
    runtime.run()
    assert reasoner.context is not None
    assert reasoner.context.relevant_learning == (record,)
    assert reasoner.context.learning_assessment is not None
    assert "historical" in " ".join(reasoner.context.learning_assessment.guidance).lower()
