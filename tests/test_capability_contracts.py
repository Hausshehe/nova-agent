from agent.capability_router import Capability
from nova_core.capability_contracts import (
    ActionSelectionRequest,
    ActionSelectionResponse,
    PerceptionRequest,
    PerceptionResponse,
    ReasoningRequest,
    ReasoningResponse,
    VerificationRequest,
    VerificationResponse,
    VerificationStatus,
)
from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, UiElement
from nova_core.reasoning import ReasoningContext


def _context() -> ReasoningContext:
    return ReasoningContext(
        goal=Goal("Finish test"),
        observation=Observation(
            package="com.example",
            activity="MainActivity",
            revision=3,
            elements=(UiElement(id="continue", text="Continue", clickable=True),),
        ),
    )


def test_reasoning_and_action_selection_contracts_share_context_without_provider_details():
    context = _context()

    reasoning = ReasoningRequest(context)
    action = ActionSelectionRequest(context)
    decision = Decision(Action(ActionType.TAP, target_id="continue"), "advance")

    assert reasoning.context is context
    assert action.context is context
    assert ReasoningResponse(decision, "advance").decision == decision
    assert ActionSelectionResponse(decision).decision == decision


def test_perception_contract_is_observation_in_and_observation_out():
    observation = _context().observation

    request = PerceptionRequest(observation)
    response = PerceptionResponse(observation, "one actionable Continue control")

    assert request.observation is observation
    assert response.observation is observation
    assert response.summary


def test_verification_contract_carries_before_after_execution_evidence():
    context = _context()
    decision = Decision(Action(ActionType.TAP, target_id="continue"))
    execution = ExecutionResult(accepted=True, changed=True)

    request = VerificationRequest(
        goal=context.goal,
        before=context.observation,
        decision=decision,
        execution=execution,
        after=context.observation,
    )
    response = VerificationResponse(
        VerificationStatus.PROGRESS,
        evidence=("Continue was consumed",),
        confidence=0.8,
    )

    assert request.goal == context.goal
    assert request.execution == execution
    assert response.status is VerificationStatus.PROGRESS
    assert response.confidence == 0.8


def test_verification_confidence_is_bounded():
    try:
        VerificationResponse(VerificationStatus.UNKNOWN, confidence=1.1)
    except ValueError as exc:
        assert "between 0 and 1" in str(exc)
    else:
        raise AssertionError("expected invalid confidence to fail")


def test_capability_contract_names_match_router_capabilities():
    assert {item.value for item in Capability} == {
        "reasoning",
        "perception",
        "action_selection",
        "verification",
    }
