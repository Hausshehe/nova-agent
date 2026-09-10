"""Conservative semantic completion verification for Nova Agent v2."""

from __future__ import annotations

import re

from .action_verifier import ActionExecutionVerifier
from .models import Decision, ExecutionResult, Goal, Observation, UiElement


_STATE_VERBS = {"open", "show", "display", "navigate", "go", "select", "choose"}
_COMPLETION_VERBS = {"finish", "complete", "completed", "done"}
_CHECK_ON_VERBS = {"enable", "turn", "check", "activate"}
_CHECK_OFF_VERBS = {"disable", "uncheck", "deactivate"}
_STOP_WORDS = {
    "a", "an", "the", "to", "into", "on", "in", "at", "for", "and",
    "please", "then", "screen", "page",
}
_COMPLETION_MARKERS = {"complete", "completed", "completion", "finished", "finish", "done"}


class SemanticGoalVerifier:
    """Verify completion using only explicit evidence in a fresh observation.

    The verifier deliberately fails closed when the observation does not expose
    enough state to prove the goal. It never treats a successful action alone as
    proof of an arbitrary natural-language goal.
    """

    def __init__(self) -> None:
        self._action_verifier = ActionExecutionVerifier()

    def verify(
        self,
        goal: Goal,
        before: Observation,
        decision: Decision,
        result: ExecutionResult,
        after: Observation,
    ) -> bool:
        if not result.accepted or not result.changed or before == after:
            return False

        words = _tokens(goal.text)
        if not words:
            return False

        verb = words[0]
        if verb in {"tap", "click", "back", "scroll", "type", "swipe", "wait"}:
            return self._action_verifier.verify(goal, before, decision, result, after)

        is_completion_goal = verb in _COMPLETION_VERBS or any(
            word in _COMPLETION_MARKERS for word in words[1:]
        )
        if is_completion_goal:
            target_words = _completion_target_tokens(words)
        else:
            target_words = _target_tokens(words)
        if not target_words:
            return False

        if verb in _CHECK_ON_VERBS:
            return _checkable_state(after, target_words, expected=True)
        if verb in _CHECK_OFF_VERBS:
            return _checkable_state(after, target_words, expected=False)
        if verb in _STATE_VERBS:
            return _state_target_visible(before, after, target_words)
        if is_completion_goal:
            return _completion_state_visible(after, target_words)

        return False


def _tokens(text: str) -> list[str]:
    return [token for token in re.findall(r"[\w]+", text.casefold()) if token]


def _target_tokens(words: list[str]) -> set[str]:
    return {
        word for word in words[1:]
        if word not in _STOP_WORDS and word not in {"up", "off", "down"}
    }


def _completion_target_tokens(words: list[str]) -> set[str]:
    return {
        word for word in words
        if word not in _STOP_WORDS
        and word not in _COMPLETION_MARKERS
        and word not in {"up", "off", "down"}
    }


def _element_tokens(element: UiElement) -> set[str]:
    return set(_tokens(f"{element.text} {element.content_description}"))


def _matches(element: UiElement, target_words: set[str]) -> bool:
    return target_words.issubset(_element_tokens(element))


def _state_target_visible(
    before: Observation,
    after: Observation,
    target_words: set[str],
) -> bool:
    after_matches = [
        element for element in after.elements
        if element.visible and _matches(element, target_words)
    ]
    if not after_matches:
        return False

    # A changed activity is strong evidence of navigation. Otherwise require
    # the target to have become visible, avoiding false positives when the same
    # label was already present on the original screen.
    if before.activity != after.activity:
        return True

    before_visible = any(
        element.visible and _matches(element, target_words)
        for element in before.elements
    )
    return not before_visible


def _completion_state_visible(
    observation: Observation,
    target_words: set[str],
) -> bool:
    """Require explicit completion evidence in the current observation.

    Accessibility trees do not always preserve a human-visible sentence in one
    node. A status can expose ``Multi-Step Test`` and ``completed`` as separate
    nodes, for example. We therefore accept completion only when the current
    observation collectively exposes every requested target token and an
    explicit completion marker. This remains evidence-based and does not infer
    completion from a successful button click alone.
    """
    visible_elements = [element for element in observation.elements if element.visible]
    if not visible_elements:
        return False

    visible_tokens = set().union(*(_element_tokens(element) for element in visible_elements))
    has_target = target_words.issubset(visible_tokens)
    has_completion_marker = any(
        bool(_element_tokens(element) & _COMPLETION_MARKERS)
        for element in visible_elements
    )
    return has_target and has_completion_marker


def _checkable_state(
    observation: Observation,
    target_words: set[str],
    *,
    expected: bool,
) -> bool:
    return any(
        element.visible
        and element.checkable
        and element.checked is expected
        and _matches(element, target_words)
        for element in observation.elements
    )
