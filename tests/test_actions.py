import pytest

from agent.actions import ActionKind, AgentAction


def test_action_round_trip() -> None:
    action = AgentAction(
        ActionKind.CLICK,
        {"text": "Settings"},
        "The Settings control matches the requested goal.",
    )

    restored = AgentAction.from_dict(action.to_dict())

    assert restored.kind is ActionKind.CLICK
    assert restored.params == {"text": "Settings"}
    assert restored.rationale.startswith("The Settings")


def test_action_defaults_missing_params_and_reasoning() -> None:
    action = AgentAction.from_dict({"action": "wait"})

    assert action.kind is ActionKind.WAIT
    assert action.params == {}
    assert action.rationale == ""


def test_unknown_action_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported action"):
        AgentAction.from_dict({"action": "teleport"})


def test_non_mapping_params_are_rejected() -> None:
    with pytest.raises(TypeError, match="params"):
        AgentAction.from_dict({"action": "click", "params": "Settings"})
