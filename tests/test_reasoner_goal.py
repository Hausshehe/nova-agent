from agent.core import UIElement, WorldState
from agent.deterministic_reasoner import DeterministicReasoner
from agent.goal_evaluator import GoalEvaluator
from agent.reasoning_context import build_reasoning_context


def state(*elements):
    return WorldState(package="com.hausshehe.nova", activity="MainActivity", elements=tuple(elements))


def test_goal_evaluator_does_not_accept_action_success_alone():
    current = state(UIElement("n1", text="Start Navigation Sequence", clickable=True))
    assert GoalEvaluator().evaluate("Complete Navigation Sequence", current) is False


def test_goal_evaluator_accepts_visible_completion_phrase():
    current = state(UIElement("n1", text="Navigation Complete", clickable=False))
    assert GoalEvaluator().evaluate("Navigation Complete", current) is True


def test_reasoner_selects_best_matching_target():
    current = state(
        UIElement("n1", text="Settings", clickable=True),
        UIElement("n2", text="Start Navigation Sequence", clickable=True),
    )
    decision = DeterministicReasoner().plan(
        build_reasoning_context("Start Navigation Sequence", current, ())
    )
    assert decision.action.target.element_id == "n2"


def test_reasoner_avoids_used_matching_target_when_recovery_is_possible():
    current = state(
        UIElement("n6", text="Start Navigation Sequence", clickable=True),
        UIElement("n8", text="Start Navigation Recovery", clickable=True),
    )
    history = ({"step": 1, "target_id": "n6", "accepted": True, "changed": True, "verified": False},)
    decision = DeterministicReasoner().plan(
        build_reasoning_context("Start Navigation", current, history)
    )
    assert decision.action.target.element_id == "n8"
