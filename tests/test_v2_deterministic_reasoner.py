import pytest

from nova_core.deterministic_reasoner import DeterministicReasoner
from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal, Observation, UiElement
from nova_core.reasoning import ReasoningContext, ReasoningStep


def context(goal, elements, history=()):
    return ReasoningContext(
        goal=Goal(goal),
        observation=Observation("pkg", "activity", tuple(elements), revision=1),
        history=tuple(history),
    )


def test_selects_exact_visible_clickable_target():
    decision = DeterministicReasoner().decide(
        context(
            "Tap Test Navigation Action",
            [
                UiElement("wrong", text="Navigation", clickable=True),
                UiElement("right", text="Test Navigation Action", clickable=True),
            ],
        )
    )
    assert decision.action == Action(ActionType.TAP, target_id="right")


def test_content_description_can_match_goal():
    decision = DeterministicReasoner().decide(
        context(
            "open settings",
            [UiElement("settings", content_description="Open Settings", clickable=True)],
        )
    )
    assert decision.action.target_id == "settings"


def test_state_goal_can_select_direct_target_without_state_verb_in_label():
    decision = DeterministicReasoner().decide(
        context(
            "Open Navigation",
            [
                UiElement("unrelated", text="Navigate to Settings", clickable=True),
                UiElement("navigation", text="Navigation", clickable=True),
            ],
        )
    )
    assert decision.action == Action(ActionType.TAP, target_id="navigation")


def test_state_goal_requires_all_meaningful_target_tokens():
    with pytest.raises(ValueError, match="no visible enabled clickable element"):
        DeterministicReasoner().decide(
            context(
                "Open Navigation Settings",
                [
                    UiElement("navigation", text="Navigation", clickable=True),
                    UiElement("settings", text="Settings", clickable=True),
                ],
            )
        )


def test_state_goal_ignores_non_viable_matching_target():
    decision = DeterministicReasoner().decide(
        context(
            "Open Navigation",
            [
                UiElement("hidden", text="Navigation", clickable=True, visible=False),
                UiElement("disabled", text="Navigation", clickable=True, enabled=False),
                UiElement("label", text="Navigation", clickable=False),
                UiElement("usable", text="Navigation", clickable=True),
            ],
        )
    )
    assert decision.action.target_id == "usable"


def test_ignores_invisible_disabled_and_non_clickable_matches():
    decision = DeterministicReasoner().decide(
        context(
            "Continue",
            [
                UiElement("hidden", text="Continue", clickable=True, visible=False),
                UiElement("disabled", text="Continue", clickable=True, enabled=False),
                UiElement("label", text="Continue", clickable=False),
                UiElement("usable", text="Continue", clickable=True),
            ],
        )
    )
    assert decision.action.target_id == "usable"


def test_history_avoids_previously_attempted_matching_target():
    history = (
        ReasoningStep(
            decision=Decision(Action(ActionType.TAP, target_id="first")),
            execution=ExecutionResult(accepted=True, changed=True),
        ),
    )
    decision = DeterministicReasoner().decide(
        context(
            "Continue",
            [
                UiElement("first", text="Continue", clickable=True),
                UiElement("second", text="Continue", clickable=True),
            ],
            history,
        )
    )
    assert decision.action.target_id == "second"


def test_history_avoids_previously_attempted_state_target():
    history = (
        ReasoningStep(
            decision=Decision(Action(ActionType.TAP, target_id="navigation")),
            execution=ExecutionResult(accepted=True, changed=True),
        ),
    )
    with pytest.raises(ValueError, match="already been attempted"):
        DeterministicReasoner().decide(
            context("Open Navigation", [UiElement("navigation", text="Navigation", clickable=True)], history)
        )


def test_exhausted_matching_targets_fail_closed():
    history = (
        ReasoningStep(
            decision=Decision(Action(ActionType.TAP, target_id="only")),
            execution=ExecutionResult(accepted=True, changed=True),
        ),
    )
    with pytest.raises(ValueError, match="already been attempted"):
        DeterministicReasoner().decide(
            context("Continue", [UiElement("only", text="Continue", clickable=True)], history)
        )


def test_no_match_fails_closed():
    with pytest.raises(ValueError, match="no visible enabled clickable element"):
        DeterministicReasoner().decide(
            context("Finish", [UiElement("other", text="Cancel", clickable=True)])
        )


def test_tie_breaking_is_stable_by_observation_order():
    decision = DeterministicReasoner().decide(
        context(
            "open settings",
            [
                UiElement("first", text="Settings", clickable=True),
                UiElement("second", text="Settings", clickable=True),
            ],
        )
    )
    assert decision.action.target_id == "first"
