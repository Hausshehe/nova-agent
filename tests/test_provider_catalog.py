from agent.capability import Capability
from agent.provider_catalog import PROVIDER_PROFILE_MAP, PROVIDER_PROFILES, SUPPORTED_PROVIDERS


def test_catalog_names_and_profiles_share_one_source_of_truth():
    assert tuple(profile.name for profile in PROVIDER_PROFILES) == SUPPORTED_PROVIDERS
    assert tuple(PROVIDER_PROFILE_MAP) == SUPPORTED_PROVIDERS


def test_catalog_declares_only_capabilities_current_adapters_serve():
    expected = frozenset({Capability.REASONING, Capability.PLANNING, Capability.ACTION_SELECTION})
    assert all(profile.capabilities == expected for profile in PROVIDER_PROFILES)


def test_catalog_exposes_derived_capability_coverage_without_faking_support():
    from agent.provider_catalog import CAPABILITY_PROVIDERS, UNPROVISIONED_CAPABILITIES

    expected = frozenset({Capability.REASONING, Capability.PLANNING, Capability.ACTION_SELECTION})
    assert frozenset(CAPABILITY_PROVIDERS) == frozenset(Capability)
    assert all(CAPABILITY_PROVIDERS[capability] for capability in expected)
    assert UNPROVISIONED_CAPABILITIES == (
        Capability.PERCEPTION,
        Capability.VERIFICATION,
    )
    assert CAPABILITY_PROVIDERS[Capability.PERCEPTION] == ()
    assert CAPABILITY_PROVIDERS[Capability.VERIFICATION] == ()
