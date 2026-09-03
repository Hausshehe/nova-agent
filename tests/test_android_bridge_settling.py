from __future__ import annotations

from agent.android_bridge import AndroidBridge
from agent.core import UIElement, WorldState


def snapshot(observation_id: str, status: str) -> WorldState:
    return WorldState(
        package="test",
        activity="Main",
        observation_id=observation_id,
        elements=(UIElement("status", status),),
    )


def test_wait_for_fresh_observation_requires_stable_ui(monkeypatch):
    bridge = AndroidBridge(timeout=1.0)
    observations = iter(
        [
            snapshot("1", "old"),
            snapshot("2", "intermediate"),
            snapshot("3", "final"),
            snapshot("4", "final"),
        ]
    )
    monkeypatch.setattr(bridge, "observe", lambda: next(observations))
    monkeypatch.setattr("agent.android_bridge.time.sleep", lambda _: None)

    result = bridge.wait_for_fresh_observation(snapshot("1", "old"), timeout=0.5, poll_seconds=0.2)

    assert result.observation_id == "4"
    assert result.elements[0].text == "final"


def test_wait_for_fresh_observation_does_not_return_first_fresh_event(monkeypatch):
    bridge = AndroidBridge(timeout=1.0)
    observations = iter(
        [
            snapshot("1", "old"),
            snapshot("2", "new"),
            snapshot("3", "new"),
        ]
    )
    monkeypatch.setattr(bridge, "observe", lambda: next(observations))
    monkeypatch.setattr("agent.android_bridge.time.sleep", lambda _: None)

    result = bridge.wait_for_fresh_observation(snapshot("1", "old"), timeout=0.5, poll_seconds=0.2)

    assert result.observation_id == "3"
    assert result.elements[0].text == "new"
