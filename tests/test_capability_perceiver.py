from agent.capability import Capability
from agent.capability_router import CapabilityRouter, pool
from nova_core.capability_perceiver import CapabilityRoutedPerceiver
from nova_core.models import Observation


def _observation() -> Observation:
    return Observation(package="com.example", activity="MainActivity")


def test_perceiver_routes_only_through_perception_capability():
    calls = []

    def perception(prompt):
        calls.append(prompt)
        return {"summary": "one visible screen"}

    router = CapabilityRouter({
        Capability.PERCEPTION: pool([("perception-provider", perception)]),
    })

    observation = _observation()
    response = CapabilityRoutedPerceiver(router).assess(observation)

    assert response.observation is observation
    assert response.summary == "one visible screen"
    assert len(calls) == 1


def test_perceiver_preserves_authoritative_observation_when_provider_returns_invalid_observation():
    def perception(prompt):
        return {"observation": {"invented": True}, "summary": "advisory"}

    router = CapabilityRouter({
        Capability.PERCEPTION: pool([("perception-provider", perception)]),
    })

    observation = _observation()
    response = CapabilityRoutedPerceiver(router).assess(observation)

    assert response.observation is observation
    assert response.summary == "advisory"
