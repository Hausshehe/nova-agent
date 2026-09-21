from agent.capability import Capability
from agent.provider_catalog import PROVIDER_PROFILE_MAP, PROVIDER_PROFILES, SUPPORTED_PROVIDERS


def test_catalog_names_and_profiles_share_one_source_of_truth():
    assert tuple(profile.name for profile in PROVIDER_PROFILES) == SUPPORTED_PROVIDERS
    assert tuple(PROVIDER_PROFILE_MAP) == SUPPORTED_PROVIDERS


def test_catalog_declares_only_capabilities_current_adapters_serve():
    expected = frozenset({Capability.REASONING, Capability.PLANNING, Capability.ACTION_SELECTION})
    assert all(profile.capabilities == expected for profile in PROVIDER_PROFILES)
