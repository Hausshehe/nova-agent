"""Explicit capability metadata for Nova providers.

Profiles describe what a provider is allowed to serve. Routing remains separate
from provider implementation details, while capability registration can reject
an incompatible provider before it reaches runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Iterable

from .capability import Capability


@dataclass(frozen=True)
class ProviderProfile:
    """Declared capabilities for one provider identity."""

    name: str
    capabilities: FrozenSet[Capability]

    @classmethod
    def create(
        cls,
        name: str,
        capabilities: Iterable[Capability | str],
    ) -> "ProviderProfile":
        if not name:
            raise ValueError("provider profile name must not be empty")
        normalized = frozenset(
            capability if isinstance(capability, Capability) else Capability(capability)
            for capability in capabilities
        )
        if not normalized:
            raise ValueError("provider profile must declare at least one capability")
        return cls(name=name, capabilities=normalized)

    def supports(self, capability: Capability | str) -> bool:
        normalized = capability if isinstance(capability, Capability) else Capability(capability)
        return normalized in self.capabilities
