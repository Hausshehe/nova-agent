"""Capability adapter for provider-backed perception enrichment.

The Android observer remains authoritative for raw UI state. This adapter is
advisory and can only enrich an existing Observation through the perception
capability. It does not replace Android observation or invent state.
"""

from __future__ import annotations

from typing import Any, Mapping

from agent.capability_router import Capability, CapabilityRouter

from .capability_contracts import PerceptionRequest, PerceptionResponse
from .models import Observation


class CapabilityRoutedPerceiver:
    """Expose perception through the capability router without replacing observation."""

    def __init__(
        self,
        router: CapabilityRouter,
        capability: Capability = Capability.PERCEPTION,
    ) -> None:
        self._router = router
        self._capability = capability

    @staticmethod
    def _response(value: Mapping[str, Any], fallback: Observation) -> PerceptionResponse:
        observation = value.get("observation", fallback)
        if not isinstance(observation, Observation):
            observation = fallback
        summary = value.get("summary", "")
        if not isinstance(summary, str):
            raise ValueError("perception summary must be a string")
        return PerceptionResponse(observation=observation, summary=summary)

    def assess(self, observation: Observation) -> PerceptionResponse:
        request = PerceptionRequest(observation)
        prompt = (
            "Summarize the supplied Android observation for Nova's reasoning layer. "
            "Do not invent UI state or change the observation. Return a concise "
            "summary and preserve the supplied observation as the source of truth.\n\n"
            f"Observation: {request.observation!r}"
        )
        return self._response(self._router(self._capability, prompt), observation)
