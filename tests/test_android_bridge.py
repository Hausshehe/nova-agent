from agent.android_bridge import AndroidBridge
from agent.core import UIElement, WorldState


def state(observation_id, status):
    return WorldState(
        package="nova",
        activity="MainActivity",
        observation_id=observation_id,
        elements=(UIElement("status", text=status),),
    )


def test_wait_for_fresh_observation_returns_settled_latest_state(monkeypatch):
    bridge = AndroidBridge()
    states = iter(
        [
            state("1", "Primary action failed. Recovery required."),
            state("2", "Recovery completed"),
            state("3", "Recovery completed"),
        ]
    )

    monkeypatch.setattr(bridge, "observe", lambda: next(states))
    monkeypatch.setattr("agent.android_bridge.time.sleep", lambda _: None)

    result = bridge.wait_for_fresh_observation(
        state("0", "Recovery run 1: choose a recovery action"),
        timeout=1.0,
        poll_seconds=0.2,
    )

    assert result.observation_id == "3"
    assert result.elements[0].text == "Recovery completed"


def test_wait_for_fresh_observation_times_out_when_ui_never_settles(monkeypatch):
    bridge = AndroidBridge()
    current = state("1", "First state")
    monkeypatch.setattr(bridge, "observe", lambda: current)
    monkeypatch.setattr("agent.android_bridge.time.sleep", lambda _: None)

    clock = iter([0.0, 0.1, 1.1])
    monkeypatch.setattr("agent.android_bridge.time.monotonic", lambda: next(clock))

    try:
        bridge.wait_for_fresh_observation(current, timeout=1.0, poll_seconds=0.2)
    except TimeoutError as exc:
        assert "settled Android observation" in str(exc)
    else:
        raise AssertionError("expected TimeoutError")
