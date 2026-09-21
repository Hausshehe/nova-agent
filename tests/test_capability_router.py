from agent.capability import Capability
from agent.capability_router import CapabilityRouter, pool
from agent.provider_profile import ProviderProfile, capability_pool


def test_capabilities_have_independent_provider_pools():
    calls = []

    def reasoning(prompt):
        calls.append(("reasoning", prompt))
        return {"source": "cerebras"}

    def action(prompt):
        calls.append(("action", prompt))
        return {"source": "groq"}

    router = CapabilityRouter({
        Capability.REASONING: pool([("cerebras", reasoning)]),
        Capability.ACTION_SELECTION: pool([("groq", action)]),
    })

    assert router.providers(Capability.REASONING) == ("cerebras",)
    assert router.providers(Capability.ACTION_SELECTION) == ("groq",)
    assert router(Capability.REASONING, "plan") == {"source": "cerebras"}
    assert router(Capability.ACTION_SELECTION, "choose") == {"source": "groq"}
    assert calls == [("reasoning", "plan"), ("action", "choose")]


def test_same_provider_can_be_assigned_to_multiple_capabilities_without_shared_health():
    first = {"count": 0}

    def reasoning(prompt):
        first["count"] += 1
        raise RuntimeError("HTTP 429 rate limit")

    def verification(prompt):
        return {"verified": True}

    router = CapabilityRouter({
        Capability.REASONING: pool(
            [("groq", reasoning)],
            transient_retries=0,
            rate_limit_cooldown_seconds=30,
        ),
        Capability.VERIFICATION: pool([("groq", verification)]),
    })

    try:
        router(Capability.REASONING, "x")
    except RuntimeError as exc:
        assert "all reasoning providers failed" in str(exc)
    else:
        raise AssertionError("expected reasoning provider failure")

    assert router(Capability.VERIFICATION, "y") == {"verified": True}
    assert first["count"] == 1


def test_missing_capability_fails_closed():
    router = CapabilityRouter()

    try:
        router(Capability.PERCEPTION, "observe")
    except RuntimeError as exc:
        assert "perception" in str(exc)
    else:
        raise AssertionError("expected missing capability failure")


def test_profile_driven_pool_excludes_undeclared_and_incompatible_providers():
    calls = []

    def supported(prompt):
        calls.append("supported")
        return {"source": "supported"}

    def wrong_capability(prompt):
        calls.append("wrong")
        return {"source": "wrong"}

    def undeclared(prompt):
        calls.append("undeclared")
        return {"source": "undeclared"}

    profiles = (
        ProviderProfile.create("supported", [Capability.ACTION_SELECTION]),
        ProviderProfile.create("wrong", [Capability.REASONING]),
    )
    action_pool = capability_pool(
        Capability.ACTION_SELECTION,
        [
            ("supported", supported),
            ("wrong", wrong_capability),
            ("undeclared", undeclared),
        ],
        profiles,
    )

    assert action_pool.providers() == ("supported",)
    assert action_pool("choose") == {"source": "supported"}
    assert calls == ["supported"]


def test_profile_driven_pool_can_be_registered_with_matching_capability():
    responder = lambda prompt: {"source": "groq"}
    profile = ProviderProfile.create(
        "groq",
        [Capability.REASONING, Capability.ACTION_SELECTION],
    )
    router = CapabilityRouter(
        {
            Capability.ACTION_SELECTION: capability_pool(
                Capability.ACTION_SELECTION,
                [("groq", responder)],
                [profile],
            )
        },
        profiles={"groq": profile},
    )

    assert router.providers(Capability.ACTION_SELECTION) == ("groq",)
    assert router(Capability.ACTION_SELECTION, "choose") == {"source": "groq"}
