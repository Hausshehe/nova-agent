"""Single source of truth for Nova provider capability declarations.

The catalog contains metadata only. Provider adapters and routing remain separate,
so capability support cannot drift because one runtime entry point forgot to update
a second provider list.
"""

from __future__ import annotations

from .capability import Capability
from .provider_profile import ProviderProfile

SUPPORTED_PROVIDERS = (
    "groq",
    "openrouter",
    "gemini",
    "mistral",
    "cerebras",
)

PROVIDER_PROFILES = tuple(
    ProviderProfile.create(
        name,
        (Capability.REASONING, Capability.PLANNING, Capability.ACTION_SELECTION),
    )
    for name in SUPPORTED_PROVIDERS
)

PROVIDER_PROFILE_MAP = {
    profile.name: profile
    for profile in PROVIDER_PROFILES
}

# Derived capability coverage. Keep this metadata-only: a capability is eligible
# for provider routing only when at least one real adapter is declared for it.
CAPABILITY_PROVIDERS = {
    capability: tuple(
        profile.name
        for profile in PROVIDER_PROFILES
        if profile.supports(capability)
    )
    for capability in Capability
}

UNPROVISIONED_CAPABILITIES = tuple(
    capability
    for capability in Capability
    if not CAPABILITY_PROVIDERS[capability]
)
