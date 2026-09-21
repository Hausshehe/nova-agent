"""Explicit capability metadata for Nova providers.

Profiles describe what a provider is allowed to serve. Routing remains separate
from provider implementation details, while capability registration can reject
an incompatible provider before it reaches runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Iterable, Sequence

from .capability import Capability
from .provider_pool import ReasoningProviderPool, Responder


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


def capability_pool(
    capability: Capability | str,
    responders: Sequence[tuple[str, Responder]],
    profiles: Iterable[ProviderProfile],
    **kwargs: object,
) -> ReasoningProviderPool:
    """Build a pool using only providers explicitly declared for a capability.

    Configuration is fail-closed: a responder without a profile is not silently
    admitted to a capability pool. This keeps provider selection derived from
    declared capability metadata rather than from a second hand-maintained list.
    """

    normalized = capability if isinstance(capability, Capability) else Capability(capability)
    profile_map = {profile.name: profile for profile in profiles}
    selected = [
        (name, responder)
        for name, responder in responders
        if name in profile_map and profile_map[name].supports(normalized)
    ]
    return ReasoningProviderPool(selected, **kwargs)
