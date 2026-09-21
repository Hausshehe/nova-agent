"""Capability adapter for provider-backed verification."""

from __future__ import annotations

from typing import Any, Mapping

from agent.capability_router import Capability, CapabilityRouter

from .capability_contracts import VerificationRequest, VerificationResponse, VerificationStatus
from .models import Decision, ExecutionResult, Goal, Observation


class CapabilityRoutedVerifier:
    """Expose a verification capability through Nova's existing boolean port.

    The provider response must contain an explicit status. Ambiguous or missing
    status fails closed. Runtime verification remains evidence-driven because
    the adapter passes the complete before/after execution context unchanged.
    """

    def __init__(
        self,
        router: CapabilityRouter,
        capability: Capability = Capability.VERIFICATION,
    ) -> None:
        self._router = router
        self._capability = capability

    @staticmethod
    def _response(value: Mapping[str, Any]) -> VerificationResponse:
        raw_status = value.get("status")
        if not isinstance(raw_status, str):
            raise ValueError("verification provider response missing status")
        try:
            status = VerificationStatus(raw_status.casefold())
        except ValueError as exc:
            raise ValueError(f"unsupported verification status: {raw_status!r}") from exc

        raw_evidence = value.get("evidence", ())
        if isinstance(raw_evidence, str):
            evidence = (raw_evidence,)
        elif isinstance(raw_evidence, (list, tuple)):
            evidence = tuple(str(item) for item in raw_evidence)
        else:
            raise ValueError("verification evidence must be a string or sequence")

        confidence = value.get("confidence")
        if confidence is not None:
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
                raise ValueError("verification confidence must be numeric")
            confidence = float(confidence)

        return VerificationResponse(status=status, evidence=evidence, confidence=confidence)

    def assess(
        self,
        goal: Goal,
        before: Observation,
        decision: Decision,
        result: ExecutionResult,
        after: Observation,
    ) -> VerificationResponse:
        request = VerificationRequest(
            goal=goal,
            before=before,
            decision=decision,
            execution=result,
            after=after,
        )
        prompt = (
            "Assess whether the Android mission is verified from the supplied "
            "before/after evidence. Return explicit status, evidence, and optional "
            "confidence. Do not infer completion from action success alone.\n\n"
            f"Goal: {request.goal.text}\n"
            f"Before: {request.before!r}\n"
            f"Decision: {request.decision!r}\n"
            f"Execution: {request.execution!r}\n"
            f"After: {request.after!r}"
        )
        return self._response(self._router(self._capability, prompt))

    def verify(
        self,
        goal: Goal,
        before: Observation,
        decision: Decision,
        result: ExecutionResult,
        after: Observation,
    ) -> bool:
        return self.assess(goal, before, decision, result, after).status is VerificationStatus.VERIFIED
