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
        (Capability.REASONING, Capability.ACTION_SELECTION),
    )
    for name in SUPPORTED_PROVIDERS
)

PROVIDER_PROFILE_MAP = {
    profile.name: profile
    for profile in PROVIDER_PROFILES
}
