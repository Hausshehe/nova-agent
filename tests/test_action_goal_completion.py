from agent.core import Action, ActionType, Target, UIElement, WorldState
from agent.goal_evaluator import GoalEvaluator


def test_tap_action_goal_requires_matching_target():
    evaluator = GoalEvaluator()
    wrong = Action(
        ActionType.CLICK,
        Target("continue", text="Continue Multi-Step"),
    )
    right = Action(
        ActionType.CLICK,
        Target("finish", text="Finish Multi-Step"),
    )

    assert not evaluator.action_goal_satisfied("Tap Finish Multi-Step", wrong)
    assert evaluator.action_goal_satisfied("Tap Finish Multi-Step", right)


def test_action_goal_rejects_explicit_failure_evidence():
    evaluator = GoalEvaluator()
    action = Action(ActionType.CLICK, Target("finish", text="Finish Multi-Step"))
    state = WorldState(
        package="com.hausshehe.nova",
        activity="MainActivity",
        observation_id=2,
        elements=[
            UIElement(id="finish", text="Finish Multi-Step", clickable=True, enabled=True),
            UIElement(id="status", text="Complete the previous steps first", clickable=False),
        ],
    )

    assert not evaluator.action_goal_satisfied("Tap Finish Multi-Step", action, state)


def test_action_goal_still_accepts_matching_action_without_failure_evidence():
    evaluator = GoalEvaluator()
    action = Action(ActionType.CLICK, Target("finish", text="Finish Multi-Step"))
    state = WorldState(
        package="com.hausshehe.nova",
        activity="MainActivity",
        observation_id=3,
        elements=[
            UIElement(id="finish", text="Finish Multi-Step", clickable=True, enabled=True),
            UIElement(id="status", text="Multi-Step Test completed", clickable=False),
        ],
    )

    assert evaluator.action_goal_satisfied("Tap Finish Multi-Step", action, state)


def test_click_and_open_are_click_actions():
    evaluator = GoalEvaluator()
    action = Action(ActionType.CLICK, Target("settings", text="Settings"))

    assert evaluator.action_goal_satisfied("Click Settings", action)
    assert evaluator.action_goal_satisfied("Open Settings", action)


def test_back_and_wait_action_goals_require_matching_action_type():
    evaluator = GoalEvaluator()

    assert evaluator.action_goal_satisfied("Go back", Action(ActionType.BACK))
    assert not evaluator.action_goal_satisfied("Go back", Action(ActionType.WAIT))
    assert evaluator.action_goal_satisfied("Wait", Action(ActionType.WAIT))
    assert not evaluator.action_goal_satisfied("Wait", Action(ActionType.BACK))


def test_scroll_does_not_satisfy_click_action_goal():
    evaluator = GoalEvaluator()
    scroll = Action(
        ActionType.SCROLL,
        Target("scroll", text="ScrollView"),
    )

    assert not evaluator.action_goal_satisfied("Tap Finish Multi-Step", scroll)
