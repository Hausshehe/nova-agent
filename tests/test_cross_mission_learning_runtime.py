from nova_core.learning_memory import LearningMemory, MissionLearningRecord
from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, RunStatus, UiElement
from nova_core.planning import Plan, PlanStep
from nova_core.reasoning import ReasoningContext
from nova_core.reasoning_adapter import _reasoning_payload
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
            elements=(UiElement(id="button", text="Continue", clickable=True),),
        )


class Executor:
    def execute(self, action: Action) -> ExecutionResult:
        return ExecutionResult(accepted=True, changed=True)


class Planner:
    def plan(self, context: ReasoningContext) -> Plan:
        return Plan((PlanStep("continue"),))

    def replan(self, context: ReasoningContext, previous: Plan) -> Plan:
        return Plan((PlanStep("continue differently"),), revision=previous.revision + 1)


class SuccessVerifier:
    def verify(self, goal, before, decision, result, after) -> bool:
        return True


class CaptureReasoner:
    def __init__(self) -> None:
        self.context: ReasoningContext | None = None

    def decide(self, context: ReasoningContext) -> Decision:
        self.context = context
        return Decision(Action(ActionType.TAP, target_id="button"), reason="continue")


def test_runtime_records_completed_mission_into_shared_learning_memory() -> None:
    memory = LearningMemory()
    runtime = Runtime(
        Goal("Open settings"),
        Observer(),
        CaptureReasoner(),
        Executor(),
        SuccessVerifier(),
        max_steps=1,
        planner=Planner(),
        learning_memory=memory,
    )

    result = runtime.run()

    assert result.status is RunStatus.SUCCEEDED
    assert len(runtime.learning_memory.entries) == 1
    assert runtime.learning_memory.entries[0].goal == "Open settings"
    assert runtime.learning_memory.entries[0].status == "succeeded"
    assert runtime.learning_memory.entries[0].changed_actions == 1


def test_next_runtime_receives_relevant_learning_from_shared_memory() -> None:
    memory = LearningMemory(entries=(
        MissionLearningRecord("Open camera", "succeeded", 1),
        MissionLearningRecord("Open settings", "succeeded", 1),
    ))
    reasoner = CaptureReasoner()
    runtime = Runtime(
        Goal("Open settings page"),
        Observer(),
        reasoner,
        Executor(),
        SuccessVerifier(),
        max_steps=1,
        planner=Planner(),
        learning_memory=memory,
    )

    runtime.run()

    assert reasoner.context is not None
    assert [record.goal for record in reasoner.context.relevant_learning] == ["Open settings"]


def test_llm_reasoning_payload_exposes_retrieved_learning_as_historical_context() -> None:
    record = MissionLearningRecord("Open settings", "succeeded", 2, changed_actions=2)
    context = ReasoningContext(
        goal=Goal("Open settings page"),
        observation=Observation(
            package="com.example.app",
            activity="MainActivity",
            revision=1,
            elements=(UiElement(id="button", text="Continue", clickable=True),),
        ),
        relevant_learning=(record,),
    )

    payload = _reasoning_payload(context)

    assert payload["learning"]["cross_mission"] == [record.snapshot()]
    assert "Past missions are historical context" in payload["learning"]["guidance"]
