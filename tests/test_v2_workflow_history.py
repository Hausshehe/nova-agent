from nova_core.deterministic_reasoner import DeterministicReasoner
from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, UiElement
from nova_core.reasoning import ReasoningContext, ReasoningStep


def context(history=()):
    return ReasoningContext(
        goal=Goal("Finish Multi-Step Test"),
        observation=Observation(
            "pkg",
            "activity",
            (
                UiElement("start", text="Multi-Step Test", clickable=True),
                UiElement("continue", text="Continue Multi-Step", clickable=True),
                UiElement("finish", text="Finish Multi-Step", clickable=True),
            ),
            revision=1,
        ),
        history=tuple(history),
    )


def step(target_id, label):
    return ReasoningStep(
        decision=Decision(
            Action(ActionType.TAP, target_id=target_id),
            target_label=label,
        ),
        execution=ExecutionResult(accepted=True, changed=True),
    )


def test_terminal_goal_starts_workflow_when_history_is_empty():
    decision = DeterministicReasoner().decide(context())
    assert decision.action.target_id == "start"
    assert decision.target_label == "Multi-Step Test"


def test_terminal_goal_uses_history_to_choose_continuation_without_step_text():
    decision = DeterministicReasoner().decide(context((step("start", "Multi-Step Test"),)))
    assert decision.action.target_id == "continue"
    assert decision.target_label == "Continue Multi-Step"


def test_terminal_goal_selects_finish_after_history_shows_continuation():
    history = (
        step("start", "Multi-Step Test"),
        step("continue", "Continue Multi-Step"),
    )
    decision = DeterministicReasoner().decide(context(history))
    assert decision.action.target_id == "finish"
    assert decision.target_label == "Finish Multi-Step"
