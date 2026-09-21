"""Authoritative deterministic verification with optional AI evidence.

The deterministic verifier remains the only source allowed to declare a mission
complete. An AI verifier may provide supplementary evidence when deterministic
verification does not prove completion, but its answer can never override that
decision.
"""

from __future__ import annotations

from typing import Any

from .capability_contracts import VerificationResponse, VerificationStatus
from .capability_verifier import CapabilityRoutedVerifier
from .models import Decision, ExecutionResult, Goal, Observation
from .ports import Verifier


class EvidenceEnrichingVerifier:
    """Keep deterministic verification authoritative and AI verification advisory."""

    def __init__(
        self,
        authoritative: Verifier,
        advisory: CapabilityRoutedVerifier | None = None,
    ) -> None:
        self._authoritative = authoritative
        self._advisory = advisory
        self._last_advisory: VerificationResponse | None = None

    @property
    def last_advisory(self) -> VerificationResponse | None:
        return self._last_advisory

    def verify(
        self,
        goal: Goal,
        before: Observation,
        decision: Decision,
        result: ExecutionResult,
        after: Observation,
    ) -> bool:
        authoritative = self._authoritative.verify(
            goal, before, decision, result, after
        )
        self._last_advisory = None

        if authoritative or self._advisory is None:
            return authoritative

        try:
            self._last_advisory = self._advisory.assess(
                goal, before, decision, result, after
            )
        except (ValueError, RuntimeError, TypeError):
            # Advisory intelligence must never destabilize authoritative
            # verification. The deterministic result remains the answer.
            self._last_advisory = None

        return authoritative

    def advisory_verified(self) -> bool:
        """Return advisory completion only as an observation, never authority."""
        return (
            self._last_advisory is not None
            and self._last_advisory.status is VerificationStatus.VERIFIED
        )
