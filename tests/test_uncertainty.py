from nova_core.mission_state import MissionState
from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation
from nova_core.runtime_brain import RuntimeBrain


def _observation(revision: int = 1) -> Observation:
    return Observation(package="com.example", activity="MainActivity", revision=revision)


def test_no_evidence_is_explicitly_uncertain() -> None:
    state = MissionState(goal=Goal("Finish task"))

    assert state.uncertainty.level == "high"
    assert "current UI state" in state.uncertainty.unknowns
    assert state.reasoning_snapshot()["uncertainty"]["level"] == "high"


def test_changed_action_is_progressing_but_goal_remains_uncertain() -> None:
    state = MissionState(goal=Goal("Finish task")).observed(_observation())
    state = state.decided(Decision(action=Action(ActionType.TAP, target_id="button"), target_label="Continue"))
    state = state.executed(ExecutionResult(accepted=True, changed=True))

    assert state.assessment["status"] == "progressing"
    assert state.assessment["confidence"] == "medium"
    assert state.uncertainty.level == "medium"
    assert "goal completion" in state.uncertainty.unknowns


def test_stalled_action_has_high_uncertainty() -> None:
    state = MissionState(goal=Goal("Finish task")).observed(_observation())
    state = state.decided(Decision(action=Action(ActionType.TAP, target_id="button"), target_label="Continue"))
    state = state.executed(ExecutionResult(accepted=True, changed=False))

    assert state.assessment["status"] == "stalled"
    assert state.uncertainty.level == "high"
    assert "whether the action had the intended effect" in state.uncertainty.unknowns


def test_verified_goal_reduces_uncertainty() -> None:
    state = MissionState(goal=Goal("Finish task")).verified(_observation(2), True)

    assert state.assessment == {"status": "verified", "confidence": "high", "basis": "goal verifier"}
    assert state.uncertainty.level == "low"
    assert state.uncertainty.unknowns == ()


def test_runtime_brain_propagates_uncertainty_into_reasoning_context() -> None:
    brain = RuntimeBrain.create(Goal("Finish task"))
    brain.start()
    brain.record_observation(_observation())

    context = brain.reasoning_context()

    assert context.uncertainty == brain.mission.uncertainty
    assert context.uncertainty.level == "high"
