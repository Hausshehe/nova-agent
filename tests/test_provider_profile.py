import pytest

from agent.capability import Capability
from agent.capability_router import CapabilityRouter, pool
from agent.provider_profile import ProviderProfile


def test_provider_profile_declares_supported_capabilities():
    profile = ProviderProfile.create(
        "gemini",
        [Capability.PERCEPTION, Capability.VERIFICATION],
    )

    assert profile.name == "gemini"
    assert profile.supports(Capability.PERCEPTION)
    assert profile.supports("verification")
    assert not profile.supports(Capability.ACTION_SELECTION)


def test_router_rejects_provider_without_declared_capability():
    router = CapabilityRouter(
        profiles={
            "groq": ProviderProfile.create("groq", [Capability.ACTION_SELECTION]),
        }
    )

    with pytest.raises(ValueError, match="does not support capability 'reasoning'"):
        router.register(
            Capability.REASONING,
            pool([("groq", lambda prompt: {"source": "groq"})]),
        )


def test_router_accepts_specialized_provider_for_declared_capability():
    router = CapabilityRouter(
        profiles={
            "cerebras": ProviderProfile.create("cerebras", [Capability.REASONING]),
        }
    )

    router.register(
        Capability.REASONING,
        pool([("cerebras", lambda prompt: {"source": "cerebras"})]),
    )

    assert router.providers(Capability.REASONING) == ("cerebras",)


def test_profile_added_after_pool_registration_is_validated():
    router = CapabilityRouter({
        Capability.ACTION_SELECTION: pool([("gemini", lambda prompt: {"source": "gemini"})]),
    })

    with pytest.raises(ValueError, match="does not support capability 'action_selection'"):
        router.register_profile(
            ProviderProfile.create("gemini", [Capability.PERCEPTION]),
        )

    assert router.profiles() == ()
