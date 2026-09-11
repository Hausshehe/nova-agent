from nova_core.mission_state import MissionState
from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, UiElement


def _observation(revision: int, *elements: UiElement) -> Observation:
    return Observation(
        package="com.example",
        activity="MainActivity",
        elements=tuple(elements),
        revision=revision,
    )


def test_fresh_observation_resolves_intended_effect_unknown_after_unchanged_action() -> None:
    goal = Goal("Finish setup")
    initial = _observation(
        1,
        UiElement(id="continue", text="Continue", clickable=True),
        UiElement(id="help", text="Help", clickable=True),
    )
    after = _observation(
        2,
        UiElement(id="continue", text="Continue", clickable=True),
        UiElement(id="help", text="Help", clickable=True),
    )

    mission = MissionState(goal).observed(initial)
    mission = mission.decided(Decision(Action(ActionType.TAP, target_id="continue"), target_label="Continue"))
    mission = mission.executed(ExecutionResult(accepted=True, changed=False))

    assert "whether the action had the intended effect" in mission.uncertainty.unknowns

    updated = mission.verified(after, goal_achieved=False)

    assert "whether the action had the intended effect" not in updated.uncertainty.unknowns
    assert "whether another action is required" in updated.uncertainty.unknowns
    assert "whether the action had the intended effect" in updated.reasoning_snapshot()["resolved_unknowns"]


def test_new_decision_does_not_inherit_old_resolved_unknowns() -> None:
    goal = Goal("Finish setup")
    initial = _observation(1, UiElement(id="continue", text="Continue", clickable=True))
    after = _observation(2, UiElement(id="continue", text="Continue", clickable=True))

    mission = MissionState(goal).observed(initial)
    mission = mission.decided(Decision(Action(ActionType.TAP, target_id="continue"), target_label="Continue"))
    mission = mission.executed(ExecutionResult(accepted=True, changed=False))
    mission = mission.verified(after, goal_achieved=False)

    assert "whether the action had the intended effect" not in mission.uncertainty.unknowns

    next_mission = mission.decided(
        Decision(Action(ActionType.TAP, target_id="continue"), target_label="Continue")
    )
    next_mission = next_mission.executed(ExecutionResult(accepted=True, changed=False))

    assert "whether the action had the intended effect" in next_mission.uncertainty.unknowns


def test_stale_observation_does_not_claim_new_evidence() -> None:
    goal = Goal("Finish setup")
    observation = _observation(4, UiElement(id="continue", text="Continue", clickable=True))

    mission = MissionState(goal).observed(observation)
    mission = mission.decided(Decision(Action(ActionType.TAP, target_id="continue"), target_label="Continue"))
    mission = mission.executed(ExecutionResult(accepted=True, changed=False))
    updated = mission.verified(observation, goal_achieved=False)

    assert "whether the action had the intended effect" in updated.uncertainty.unknowns
    assert updated.resolved_unknowns == ()
