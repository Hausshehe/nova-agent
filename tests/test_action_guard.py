from agent.action_guard import ActionGuard
from agent.core import Action, ActionType, Target, UIElement, WorldState
from agent.task_effect import TaskEffect, TaskEffectResult
from agent.task_state import TaskState


def _state(status: str, observation_id: str = "1") -> WorldState:
    return WorldState(
        package="test",
        activity="Main",
        observation_id=observation_id,
        elements=(
            UIElement(id="finish", text="Finish", clickable=True),
            UIElement(id="continue", text="Continue", clickable=True),
            UIElement(id="status", text=status, clickable=False),
        ),
    )


def _blocked_task(state: WorldState) -> tuple[TaskState, Action]:
    action = Action(ActionType.CLICK, Target("finish", "Finish"))
    task = TaskState()
    task.apply(
        action,
        TaskEffectResult(TaskEffect.BLOCKED, "Previous steps required"),
        state,
        state,
    )
    return task, action


def test_guard_blocks_action_with_active_constraint():
    state = _state("Previous steps required")
    task, action = _blocked_task(state)

    result = ActionGuard().check(action, state, task)

    assert not result.allowed
    assert result.evidence == "Previous steps required"


def test_guard_allows_different_action():
    state = _state("Previous steps required")
    task, _ = _blocked_task(state)
    action = Action(ActionType.CLICK, Target("continue", "Continue"))

    result = ActionGuard().check(action, state, task)

    assert result.allowed


def test_guard_allows_constrained_action_after_state_changes():
    blocked_state = _state("Previous steps required", "1")
    changed_state = _state("Step advanced", "2")
    task, action = _blocked_task(blocked_state)

    result = ActionGuard().check(action, changed_state, task)

    assert result.allowed


def test_guard_does_not_execute_or_mutate_task_state():
    state = _state("Previous steps required")
    task, action = _blocked_task(state)
    before_constraints = task.active_constraints(state)

    result = ActionGuard().check(action, state, task)

    assert not result.allowed
    assert task.active_constraints(state) == before_constraints
