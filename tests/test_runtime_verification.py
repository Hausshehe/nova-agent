from agent.capability_router import Capability, CapabilityRouter, pool
from nova_core.capability_contracts import VerificationStatus
from nova_core.capability_verifier import CapabilityRoutedVerifier
from nova_core.evidence_verifier import EvidenceEnrichingVerifier
from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, RunStatus, UiElement
from nova_core.runtime import Runtime


class Observer:
    def __init__(self, after_marker: bool = False):
        self.calls = 0
        self.after_marker = after_marker

    def observe(self):
        self.calls += 1
        elements = ()
        if self.after_marker and self.calls > 1:
            elements = (UiElement(id="status", text="Finish test completed"),)
        return Observation("pkg", "MainActivity", elements=elements, revision=self.calls)


class Reasoner:
    def decide(self, context):
        return Decision(Action(ActionType.TAP, target_id="target"))


class Executor:
    def execute(self, action):
        return ExecutionResult(accepted=True, changed=True)


class AuthoritativeVerifier:
    def __init__(self, achieved):
        self.achieved = achieved
        self.calls = 0

    def verify(self, goal, before, decision, result, after):
        self.calls += 1
        return self.achieved


def _advisory(responder):
    return CapabilityRoutedVerifier(
        CapabilityRouter({
            Capability.VERIFICATION: pool(
                [("verify-model", responder)],
                transient_retries=0,
            )
        })
    )


def test_runtime_keeps_advisory_verification_from_declaring_success():
    calls = []

    def responder(prompt):
        calls.append(prompt)
        return {
            "status": "verified",
            "evidence": ["model says complete"],
            "confidence": 0.99,
        }

    authoritative = AuthoritativeVerifier(False)
    runtime = Runtime(
        Goal("Finish test"),
        Observer(),
        Reasoner(),
        Executor(),
        EvidenceEnrichingVerifier(authoritative, _advisory(responder)),
        max_steps=1,
    )

    result = runtime.run()

    assert result.status is RunStatus.FAILED
    assert authoritative.calls == 1
    assert len(calls) == 1


def test_runtime_skips_advisory_verification_when_authoritative_verifier_succeeds():
    calls = []

    def responder(prompt):
        calls.append(prompt)
        return {"status": "verified"}

    authoritative = AuthoritativeVerifier(True)
    runtime = Runtime(
        Goal("Finish test"),
        Observer(after_marker=True),
        Reasoner(),
        Executor(),
        EvidenceEnrichingVerifier(authoritative, _advisory(responder)),
        max_steps=1,
    )

    result = runtime.run()

    assert result.status is RunStatus.SUCCEEDED
    assert authoritative.calls == 1
    assert calls == []


def test_runtime_survives_advisory_verifier_failure():
    def responder(prompt):
        raise RuntimeError("verification provider unavailable")

    authoritative = AuthoritativeVerifier(False)
    runtime = Runtime(
        Goal("Finish test"),
        Observer(),
        Reasoner(),
        Executor(),
        EvidenceEnrichingVerifier(authoritative, _advisory(responder)),
        max_steps=1,
    )

    result = runtime.run()

    assert result.status is RunStatus.FAILED
    assert authoritative.calls == 1
