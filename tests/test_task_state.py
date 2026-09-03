from agent.core import Action, ActionType, ExecutionResult, Target, UIElement, WorldState
from agent.task_effect import TaskEffect, TaskEffectResult
from agent.task_state import TaskState, state_fingerprint


def _state(status: str, observation_id: str = "1") -> WorldState:
    return WorldState(
        package="test",
        activity="Main",
        observation_id=observation_id,
        elements=(
            UIElement(id="finish", text="Finish", clickable=True),
            UIElement(id="status", text=status, clickable=False),
        ),
    )


def test_blocked_effect_creates_state_scoped_constraint():
    state = _state("Previous steps required")
    action = Action(ActionType.CLICK, Target("finish", "Finish"))
    task = TaskState()

    task.apply(
        action,
        TaskEffectResult(TaskEffect.BLOCKED, "Previous steps required"),
        state,
        state,
    )

    assert task.effect is TaskEffect.BLOCKED
    assert task.is_constrained(action, state)
    assert len(task.active_constraints(state)) == 1
    assert task.active_constraints(state)[0].evidence == "Previous steps required"


def test_constraint_expires_when_observed_state_changes():
    before = _state("Previous steps required", "1")
    after = _state("Step advanced", "2")
    action = Action(ActionType.CLICK, Target("finish", "Finish"))
    task = TaskState()

    task.apply(
        action,
        TaskEffectResult(TaskEffect.BLOCKED, "Previous steps required"),
        before,
        before,
    )

    assert task.is_constrained(action, before)
    task.apply(action, TaskEffectResult(TaskEffect.PROGRESSED), before, after)
    assert not task.is_constrained(action, after)
    assert task.active_constraints(after) == ()


def test_constraint_does_not_match_a_different_action():
    state = _state("Previous steps required")
    task = TaskState()
    blocked = Action(ActionType.CLICK, Target("finish", "Finish"))
    other = Action(ActionType.CLICK, Target("continue", "Continue"))

    task.apply(
        blocked,
        TaskEffectResult(TaskEffect.BLOCKED, "Previous steps required"),
        state,
        state,
    )

    assert task.is_constrained(blocked, state)
    assert not task.is_constrained(other, state)


def test_reset_clears_effect_and_constraints():
    state = _state("Previous steps required")
    action = Action(ActionType.CLICK, Target("finish", "Finish"))
    task = TaskState()
    task.apply(
        action,
        TaskEffectResult(TaskEffect.BLOCKED, "Previous steps required"),
        state,
        state,
    )

    task.reset()

    assert task.effect is TaskEffect.UNKNOWN
    assert task.effect_evidence == ""
    assert task.constraints == []


def test_state_fingerprint_ignores_observation_metadata():
    first = _state("Ready", "1")
    second = _state("Ready", "2")

    assert state_fingerprint(first) == state_fingerprint(second)
