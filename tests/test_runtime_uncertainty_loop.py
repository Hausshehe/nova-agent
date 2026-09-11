from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, UiElement
from nova_core.planning import Plan, PlanStep
from nova_core.reasoning import ReasoningContext
from nova_core.runtime import Runtime
from nova_core.state_machine import RunState


class EvidenceObserver:
    """Returns a new observation revision after every runtime observation."""

    def __init__(self):
        self.revision = 0

    def observe(self):
        self.revision += 1
        return Observation(
            package="com.example.app",
            activity="MainActivity",
            revision=self.revision,
            elements=(
                UiElement(id="probe", text="Continue", clickable=True),
                UiElement(id="alternative", text="Open details", clickable=True),
            ),
        )


class EvidencePlanner:
    def plan(self, context: ReasoningContext) -> Plan:
        return Plan((PlanStep("investigate current state"),), revision=0)

    def replan(self, context: ReasoningContext, previous: Plan) -> Plan:
        return Plan((PlanStep("investigate current state"),), revision=previous.revision + 1)


class EvidenceReasoner:
    def __init__(self):
        self.contexts = []
        self.decisions = []

    def decide(self, context: ReasoningContext) -> Decision:
        self.contexts.append(context)
        if len(self.decisions) == 0:
            decision = Decision(
                Action(ActionType.TAP, target_id="probe"),
                reason="Use the visible probe to gather evidence.",
                target_label="Continue",
            )
        else:
            resolution = context.uncertainty_resolution
            assert resolution is not None
            candidate_ids = [item.action.target_id for item in resolution.candidates]
            assert "probe" not in candidate_ids
            assert "alternative" in candidate_ids
            decision = Decision(
                Action(ActionType.TAP, target_id="alternative"),
                reason="Fresh observation showed the probe did not change the state; use the alternative.",
                target_label="Open details",
            )
        self.decisions.append(decision)
        return decision


class EvidenceExecutor:
    def __init__(self):
        self.actions = []

    def execute(self, action):
        self.actions.append(action)
        if action.target_id == "probe":
            return ExecutionResult(accepted=True, changed=False)
        return ExecutionResult(accepted=True, changed=True)


class EvidenceVerifier:
    def verify(self, goal, before, decision, result, after):
        return decision.action.target_id == "alternative" and result.accepted and result.changed


def test_runtime_uses_fresh_observation_to_change_next_decision() -> None:
    reasoner = EvidenceReasoner()
    executor = EvidenceExecutor()
    runtime = Runtime(
        Goal("Finish setup"),
        EvidenceObserver(),
        reasoner,
        executor,
        EvidenceVerifier(),
        max_steps=2,
        planner=EvidencePlanner(),
    )

    result = runtime.run()

    assert result.status.value == "succeeded"
    assert [action.target_id for action in executor.actions] == ["probe", "alternative"]
    assert len(reasoner.contexts) == 2

    first_context, second_context = reasoner.contexts
    assert first_context.observation.revision == 1
    assert first_context.mission_state is not None
    assert "whether the action had the intended effect" in first_context.uncertainty.unknowns

    assert second_context.observation.revision == 2
    assert second_context.mission_state is not None
    assert "whether the action had the intended effect" not in second_context.uncertainty.unknowns
    assert "whether another action is required" in second_context.uncertainty.unknowns
    assert "whether the action had the intended effect" in second_context.mission_state.resolved_unknowns


def test_runtime_does_not_repeat_evidence_action_after_fresh_unchanged_observation() -> None:
    reasoner = EvidenceReasoner()
    executor = EvidenceExecutor()
    runtime = Runtime(
        Goal("Finish setup"),
        EvidenceObserver(),
        reasoner,
        executor,
        EvidenceVerifier(),
        max_steps=2,
        planner=EvidencePlanner(),
    )

    runtime.run()

    assert reasoner.decisions[0].action.target_id == "probe"
    assert reasoner.decisions[1].action.target_id == "alternative"
    assert reasoner.contexts[1].uncertainty_resolution is not None
    assert all(
        candidate.action.target_id != "probe"
        for candidate in reasoner.contexts[1].uncertainty_resolution.candidates
    )
