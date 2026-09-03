from agent.core import UIElement, WorldState
from agent.goal_evaluator import GoalEvaluator


def test_action_goal_does_not_fall_back_to_state_goal_match() -> None:
    evaluator = GoalEvaluator()
    state = WorldState(
        package="com.hausshehe.nova",
        activity="MainActivity",
        observation_id=2,
        elements=[
            UIElement(
                id="finish",
                text="Finish Multi-Step",
                clickable=True,
                enabled=True,
                visible=False,
            ),
            UIElement(
                id="status",
                text="Complete the previous steps first",
                clickable=False,
                enabled=True,
                visible=True,
            ),
        ],
    )

    assert evaluator.is_action_goal("Tap Finish Multi-Step")
    assert not evaluator.evaluate("Tap Finish Multi-Step", state)
