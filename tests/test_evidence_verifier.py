from agent.capability_router import Capability, CapabilityRouter, pool
from nova_core.capability_contracts import VerificationStatus
from nova_core.capability_verifier import CapabilityRoutedVerifier
from nova_core.evidence_verifier import EvidenceEnrichingVerifier
from nova_core.models import (
    Action,
    ActionType,
    Decision,
    ExecutionResult,
    Goal,
    Observation,
    UiElement,
)
from nova_core.semantic_verifier import SemanticGoalVerifier


def _observation(*elements, activity="Main"):
    return Observation(package="com.example.app", activity=activity, elements=tuple(elements))


def _decision():
    return Decision(Action(type=ActionType.TAP, target_id="target"))


def _inputs():
    return (
        Goal("Finish test"),
        _observation(),
        _decision(),
        ExecutionResult(accepted=True, changed=True),
        _observation(),
    )


def _advisory(status="verified"):
    router = CapabilityRouter({
        Capability.VERIFICATION: pool(
            [("verify-model", lambda prompt: {
                "status": status,
                "evidence": ["model assessment"],
                "confidence": 0.8,
            })],
            transient_retries=0,
        )
    })
    return CapabilityRoutedVerifier(router)


def test_deterministic_verification_remains_authoritative():
    verifier = EvidenceEnrichingVerifier(
        authoritative=SemanticGoalVerifier(),
        advisory=_advisory("verified"),
    )
    goal, before, decision, execution, after = _inputs()

    assert not verifier.verify(goal, before, decision, execution, after)
    assert verifier.advisory_verified()
    assert verifier.last_advisory is not None
    assert verifier.last_advisory.status is VerificationStatus.VERIFIED


def test_advisory_is_not_called_when_deterministic_verification_succeeds():
    calls = []

    def responder(prompt):
        calls.append(prompt)
        return {"status": "verified"}

    advisory = CapabilityRoutedVerifier(
        CapabilityRouter({
            Capability.VERIFICATION: pool(
                [("verify-model", responder)], transient_retries=0
            )
        })
    )
    verifier = EvidenceEnrichingVerifier(SemanticGoalVerifier(), advisory)

    before = _observation()
    after = _observation(
        UiElement(id="status", text="Multi-Step Test completed")
    )
    execution = ExecutionResult(accepted=True, changed=True)

    assert verifier.verify(
        Goal("Finish Multi-Step Test"), before, _decision(), execution, after
    )
    assert calls == []
    assert verifier.last_advisory is None


def test_advisory_failure_does_not_break_deterministic_verification():
    class FailingVerifier:
        def assess(self, *args):
            raise RuntimeError("provider unavailable")

    verifier = EvidenceEnrichingVerifier(SemanticGoalVerifier(), FailingVerifier())
    goal, before, decision, execution, after = _inputs()

    assert not verifier.verify(goal, before, decision, execution, after)
    assert verifier.last_advisory is None
