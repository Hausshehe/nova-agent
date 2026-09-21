from agent.capability_router import Capability, CapabilityRouter, pool
from nova_core.capability_verifier import CapabilityRoutedVerifier
from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation


def _observation(label: str) -> Observation:
    return Observation(package="com.example.app", activity="Main", elements=())


def _decision() -> Decision:
    return Decision(Action(type=ActionType.TAP, target_id="target"))


def _inputs():
    return (
        Goal("Finish test"),
        _observation("before"),
        _decision(),
        ExecutionResult(accepted=True, changed=True),
        _observation("after"),
    )


def test_verifier_routes_to_verification_capability():
    calls = []

    def verification(prompt):
        calls.append(prompt)
        return {"status": "verified", "evidence": ["completion visible"], "confidence": 0.9}

    def action_selection(prompt):
        raise AssertionError("action-selection provider must not be used")

    router = CapabilityRouter(
        {
            Capability.VERIFICATION: pool([("verify-model", verification)], transient_retries=0),
            Capability.ACTION_SELECTION: pool([("action-model", action_selection)], transient_retries=0),
        }
    )
    verifier = CapabilityRoutedVerifier(router)

    assert verifier.verify(*_inputs())
    assert len(calls) == 1
    assert "Finish test" in calls[0]


def test_verifier_returns_structured_response_and_preserves_evidence():
    router = CapabilityRouter({
        Capability.VERIFICATION: pool(
            [("verify-model", lambda prompt: {
                "status": "progress",
                "evidence": ["screen changed", "target not complete"],
                "confidence": 0.4,
            })],
            transient_retries=0,
        )
    })

    response = CapabilityRoutedVerifier(router).assess(*_inputs())

    assert response.status.value == "progress"
    assert response.evidence == ("screen changed", "target not complete")
    assert response.confidence == 0.4


def test_verifier_fails_closed_on_missing_status():
    router = CapabilityRouter({
        Capability.VERIFICATION: pool(
            [("verify-model", lambda prompt: {})],
            transient_retries=0,
        )
    })

    try:
        CapabilityRoutedVerifier(router).verify(*_inputs())
    except ValueError as exc:
        assert "missing status" in str(exc)
    else:
        raise AssertionError("missing verification status must fail closed")


def test_verifier_rejects_unknown_status():
    router = CapabilityRouter({
        Capability.VERIFICATION: pool(
            [("verify-model", lambda prompt: {"status": "maybe"})],
            transient_retries=0,
        )
    })

    try:
        CapabilityRoutedVerifier(router).assess(*_inputs())
    except ValueError as exc:
        assert "unsupported verification status" in str(exc)
    else:
        raise AssertionError("unknown verification status must fail closed")
