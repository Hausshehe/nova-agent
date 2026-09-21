"""Runtime adapter for capability-routed action reasoning."""

from __future__ import annotations

from typing import Any, Mapping

from agent.capability_router import Capability, CapabilityRouter

from .models import Decision
from .reasoning import ReasoningContext
from .reasoning_adapter import LLMReasoner


class CapabilityRoutedReasoner:
    """Expose one capability-router pool through Nova's v2 Reasoner port.

    The runtime still owns execution and verification. This adapter only routes
    the concrete action-selection decision to the configured capability pool.
    """

    def __init__(
        self,
        router: CapabilityRouter,
        capability: Capability = Capability.ACTION_SELECTION,
    ) -> None:
        self._router = router
        self._capability = capability
        self._reasoner = LLMReasoner(self._respond)

    def _respond(self, prompt: str) -> Mapping[str, Any]:
        return self._router(self._capability, prompt)

    def decide(self, context: ReasoningContext) -> Decision:
        return self._reasoner.decide(context)
