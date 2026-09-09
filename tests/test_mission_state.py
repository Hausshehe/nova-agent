from nova_core.mission_state import MissionState
from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, UiElement
from nova_core.runtime_brain import RuntimeBrain
from nova_core.state_machine import RunState


def observation(revision: int = 1) -> Observation:
    return Observation(
        package="com.example",
        activity="MainActivity",
        elements=(UiElement(id="next", text="Next", clickable=True),),
        revision=revision,
    )


def decision() -> Decision:
    return Decision(Action(ActionType.TAP, target_id="next"), reason="advance")


def test_mission_state_derives_only_runtime_facts() -> None:
    goal = Goal("Finish the task")
    state = MissionState(goal).observed(observation()).decided(decision())
    state = state.executed(ExecutionResult(accepted=True, changed=True))
    state = state.verified(observation(2), goal_achieved=False)

    assert state.goal == goal
    assert state.observation.revision == 2
    assert state.last_decision == decision()
    assert state.last_execution == ExecutionResult(accepted=True, changed=True)
    assert state.successful_actions == 1
    assert state.changed_actions == 1
    assert state.failed_actions == 0
    assert state.goal_verified is False
    assert "last_action_type=tap" in state.progress_evidence
    assert "last_target_id=next" in state.progress_evidence
    assert "goal_verified=False" in state.progress_evidence


def test_failed_execution_is_counted_as_failure_evidence() -> None:
    state = MissionState(Goal("Recover")).decided(decision())
    state = state.executed(ExecutionResult(accepted=False, changed=False, error="blocked"))

    assert state.successful_actions == 0
    assert state.changed_actions == 0
    assert state.failed_actions == 1
    assert "last_execution_error=blocked" in state.progress_evidence


def test_runtime_brain_exposes_current_mission_state_to_reasoning() -> None:
    brain = RuntimeBrain.create(Goal("Finish the task"), max_steps=3)
    brain.start()
    current = observation()
    brain.record_observation(current)
    brain.record_decision(decision())
    brain.record_execution(ExecutionResult(accepted=True, changed=True))

    assert brain.mission.observation == current
    assert brain.mission.last_decision == decision()
    assert brain.mission.last_execution == ExecutionResult(accepted=True, changed=True)
    assert brain.mission.successful_actions == 1


def test_reasoning_context_carries_the_same_mission_state_instance() -> None:
    brain = RuntimeBrain.create(Goal("Finish the task"), max_steps=3)
    brain.start()
    brain.record_observation(observation())

    context = brain.reasoning_context()

    assert context.mission_state is brain.mission
    assert context.mission_state.observation == observation()
    assert context.mission_state.successful_actions == 0


def test_goal_verification_marks_mission_complete() -> None:
    brain = RuntimeBrain.create(Goal("Finish the task"), max_steps=1)
    brain.start()
    brain.record_observation(observation())
    brain.record_decision(decision())
    brain.record_execution(ExecutionResult(accepted=True, changed=True))
    result = brain.finish_verification(observation(2), goal_achieved=True)

    assert result is not None
    assert result.status is not None
    assert result.status.value == "succeeded"
    assert brain.state is RunState.SUCCEEDED
    assert brain.goal_verified is True
    assert brain.mission.goal_verified is True
    assert brain.mission.observation.revision == 2
