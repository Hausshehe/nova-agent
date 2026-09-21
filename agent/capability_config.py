"""Construct Nova's capability router from one provider capability catalog.

The factory is deliberately adapter-agnostic: callers supply already-built responder
callables, while the catalog remains the only authority for capability eligibility.
Unprovisioned capabilities are simply absent from the router.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from .capability import Capability
from .capability_router import CapabilityRouter
from .provider_catalog import PROVIDER_PROFILES
from .provider_pool import Responder
from .provider_profile import ProviderProfile, capability_pool


def build_capability_router(
    responders: Mapping[Capability | str, Sequence[tuple[str, Responder]]],
    *,
    profiles: Iterable[ProviderProfile] = PROVIDER_PROFILES,
    pool_kwargs: Mapping[str, object] | None = None,
) -> CapabilityRouter:
    """Build only the capability pools supported by the supplied adapters.

    Provider capability declarations are authoritative. A responder supplied for
    an undeclared capability is ignored rather than silently expanding support.
    Empty pools are omitted, so missing capabilities fail closed at router call time.
    """

    profile_tuple = tuple(profiles)
    router = CapabilityRouter(profiles={profile.name: profile for profile in profile_tuple})
    kwargs = dict(pool_kwargs or {})

    for capability, capability_responders in responders.items():
        normalized = capability if isinstance(capability, Capability) else Capability(capability)
        eligible = capability_pool(
            normalized,
            capability_responders,
            profile_tuple,
            **kwargs,
        )
        if eligible.providers():
            router.register(normalized, eligible)

    return router
