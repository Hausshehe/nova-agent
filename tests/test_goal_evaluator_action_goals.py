from agent.core import UIElement, WorldState
from agent.goal_evaluator import GoalEvaluator


def state(*texts):
    return WorldState(
        package="nova",
        observation_id="1",
        elements=tuple(UIElement(f"n{i}", text=text) for i, text in enumerate(texts)),
    )


def test_action_goal_is_not_complete_when_only_action_target_is_visible():
    current = state("Test Navigation Action")

    assert GoalEvaluator().evaluate("Tap Test Navigation Action", current) is False


def test_action_goal_is_complete_when_result_state_is_visible():
    completed = state("Navigation Action Completed")

    assert GoalEvaluator().evaluate("Tap Test Navigation Action", completed) is True


def test_state_goal_still_completes_from_visible_result_text():
    current = state("Wi-Fi", "Wi-Fi enabled")

    assert GoalEvaluator().evaluate("Wi-Fi enabled", current) is True
