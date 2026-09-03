from agent.core import Action, ActionType, ExecutionResult, Target, UIElement, WorldState
from agent.task_effect import TaskEffect, TaskEffectEvaluator


def state(*elements, observation_id="1"):
    return WorldState(observation_id=observation_id, elements=tuple(elements))


def finish_action():
    return Action(ActionType.CLICK, Target(element_id="finish", text="Finish"))


def test_rejected_action_is_failed():
    result = TaskEffectEvaluator().evaluate(
        "Tap Finish",
        finish_action(),
        ExecutionResult(False, False, error="target unavailable"),
        state(observation_id="1"),
        state(observation_id="2"),
    )

    assert result.effect is TaskEffect.FAILED
    assert result.evidence == "target unavailable"


def test_explicit_prerequisite_failure_is_blocked_even_when_click_was_accepted():
    result = TaskEffectEvaluator().evaluate(
        "Tap Finish",
        finish_action(),
        ExecutionResult(True, True),
        state(observation_id="1"),
        state(UIElement(id="status", text="Complete the previous steps first"), observation_id="2"),
    )

    assert result.effect is TaskEffect.BLOCKED
    assert result.evidence == "Complete the previous steps first"


def test_successful_action_goal_is_completed():
    result = TaskEffectEvaluator().evaluate(
        "Tap Finish",
        finish_action(),
        ExecutionResult(True, True),
        state(UIElement(id="finish", text="Finish", clickable=True), observation_id="1"),
        state(UIElement(id="status", text="Finished"), observation_id="2"),
    )

    assert result.effect is TaskEffect.COMPLETED


def test_state_change_without_completion_is_progressed():
    result = TaskEffectEvaluator().evaluate(
        "Tap Continue",
        Action(ActionType.CLICK, Target(element_id="continue", text="Continue")),
        ExecutionResult(True, True),
        state(UIElement(id="continue", text="Continue", clickable=True), observation_id="1"),
        state(UIElement(id="continue", text="Continue", clickable=True), UIElement(id="status", text="Step advanced"), observation_id="2"),
    )

    assert result.effect is TaskEffect.PROGRESSED


def test_accepted_action_without_state_change_is_unknown():
    before = state(UIElement(id="finish", text="Finish", clickable=True), observation_id="1")
    after = state(UIElement(id="finish", text="Finish", clickable=True), observation_id="1")

    result = TaskEffectEvaluator().evaluate(
        "Tap Finish",
        finish_action(),
        ExecutionResult(True, False),
        before,
        after,
    )

    assert result.effect is TaskEffect.UNKNOWN
