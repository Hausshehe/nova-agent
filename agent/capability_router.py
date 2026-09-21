"""Capability-aware routing for Nova's multi-provider AI layer.

Providers are assigned to explicit capabilities instead of one global primary/fallback
chain. The same provider may serve multiple capabilities, but each capability owns its
own bounded health state and cooldowns.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping, Sequence

from .capability import Capability
from .provider_pool import ReasoningProviderPool, Responder
from .provider_profile import ProviderProfile


class CapabilityRouter:
    """Route each AI task through its own bounded provider pool."""

    def __init__(
        self,
        pools: Mapping[Capability | str, ReasoningProviderPool] | None = None,
        profiles: Mapping[str, ProviderProfile] | None = None,
    ) -> None:
        self._pools: dict[Capability, ReasoningProviderPool] = {}
        self._profiles: dict[str, ProviderProfile] = {}
        for profile in (profiles or {}).values():
            self.register_profile(profile)
        for capability, pool in (pools or {}).items():
            self.register(capability, pool)

    @staticmethod
    def _normalize(capability: Capability | str) -> Capability:
        try:
            return capability if isinstance(capability, Capability) else Capability(capability)
        except ValueError as exc:
            raise ValueError(f"unsupported Nova capability: {capability!r}") from exc

    def register_profile(self, profile: ProviderProfile) -> None:
        if not isinstance(profile, ProviderProfile):
            raise TypeError("provider profile must be a ProviderProfile")
        for capability, pool in self._pools.items():
            if profile.name in pool.providers() and not profile.supports(capability):
                raise ValueError(
                    f"provider {profile.name!r} does not support capability {capability.value!r}"
                )
        self._profiles[profile.name] = profile

    def profiles(self) -> tuple[ProviderProfile, ...]:
        return tuple(self._profiles.values())

    def register(self, capability: Capability | str, pool: ReasoningProviderPool) -> None:
        if not isinstance(pool, ReasoningProviderPool):
            raise TypeError("capability pool must be a ReasoningProviderPool")
        normalized = self._normalize(capability)
        for provider in pool.providers():
            profile = self._profiles.get(provider)
            if profile is not None and not profile.supports(normalized):
                raise ValueError(
                    f"provider {provider!r} does not support capability {normalized.value!r}"
                )
        self._pools[normalized] = pool

    def capabilities(self) -> tuple[Capability, ...]:
        return tuple(self._pools)

    def providers(self, capability: Capability | str) -> tuple[str, ...]:
        pool = self._pools.get(self._normalize(capability))
        if pool is None:
            return ()
        return pool.providers()

    def __call__(self, capability: Capability | str, prompt: str) -> Mapping[str, Any]:
        normalized = self._normalize(capability)
        pool = self._pools.get(normalized)
        if pool is None:
            raise RuntimeError(f"no provider pool configured for capability: {normalized.value}")
        return pool(prompt)

    def health(self) -> dict[str, dict[str, dict[str, float | int]]]:
        return {capability.value: pool.health() for capability, pool in self._pools.items()}


def pool(responders: Sequence[tuple[str, Responder]], **kwargs: Any) -> ReasoningProviderPool:
    """Small construction helper used by capability configuration/tests."""
    return ReasoningProviderPool(responders, **kwargs)
