from agent.capability import Capability
from agent.capability_config import build_capability_router
from agent.provider_profile import ProviderProfile


def test_factory_builds_only_catalog_approved_capability_pools():
    calls = []

    def responder(label):
        def call(prompt):
            calls.append(label)
            return {"source": label}
        return call

    router = build_capability_router({
        Capability.REASONING: [
            ("cerebras", responder("cerebras")),
            ("unknown", responder("unknown")),
        ],
        Capability.PERCEPTION: [
            ("cerebras", responder("should-not-run")),
        ],
    })

    assert router.providers(Capability.REASONING) == ("cerebras",)
    assert router.providers(Capability.PERCEPTION) == ()
    assert router(Capability.REASONING, "reason") == {"source": "cerebras"}
    assert calls == ["cerebras"]


def test_factory_uses_custom_profiles_as_the_capability_boundary():
    def responder(prompt):
        return {"source": "special"}

    profile = ProviderProfile.create(
        "special",
        [Capability.PERCEPTION],
    )
    router = build_capability_router(
        {
            Capability.PERCEPTION: [("special", responder)],
            Capability.REASONING: [("special", responder)],
        },
        profiles=(profile,),
    )

    assert router.providers(Capability.PERCEPTION) == ("special",)
    assert router.providers(Capability.REASONING) == ()
    assert router(Capability.PERCEPTION, "inspect") == {"source": "special"}


def test_factory_omits_empty_capability_pools_so_missing_support_fails_closed():
    router = build_capability_router({
        Capability.VERIFICATION: [("cerebras", lambda prompt: {"status": "verified"})],
    })

    assert router.capabilities() == ()
    try:
        router(Capability.VERIFICATION, "verify")
    except RuntimeError as exc:
        assert "verification" in str(exc)
    else:
        raise AssertionError("expected missing verification capability")
