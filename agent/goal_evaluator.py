from __future__ import annotations

import re

from .core import Action, ActionType, WorldState, element_text


_ACTION_VERBS = {"tap", "click", "open", "back", "wait"}
_STOP_WORDS = {"a", "an", "the", "to", "of", "and", "then", "please"}
_CLICK_VERBS = {"tap", "click", "open"}
_FAILURE_PHRASES = (
    "failed",
    "failure",
    "error",
    "unable",
    "cannot",
    "can't",
    "denied",
    "invalid",
    "not allowed",
    "not permitted",
    "try again",
    "previous steps",
)


class GoalEvaluator:
    """Conservative goal completion checks based on the current UI state."""

    def is_action_goal(self, goal: str) -> bool:
        tokens = re.findall(r"[a-z0-9]+", goal.lower())
        if not tokens:
            return False
        if tokens[0] in _ACTION_VERBS:
            return True
        return len(tokens) >= 2 and tokens[:2] == ["go", "back"]

    def action_goal_satisfied(
        self,
        goal: str,
        action: Action,
        state: WorldState | None = None,
    ) -> bool:
        """Return whether an executed action satisfies an action goal."""
        tokens = re.findall(r"[a-z0-9]+", goal.lower())
        if not tokens or not self.is_action_goal(goal):
            return False

        if tokens[:2] == ["go", "back"] or tokens[0] == "back":
            return action.type is ActionType.BACK and not self._has_failure_evidence(state)
        if tokens[0] == "wait":
            return action.type is ActionType.WAIT and not self._has_failure_evidence(state)
        if tokens[0] not in _CLICK_VERBS:
            return False
        if action.type is not ActionType.CLICK or action.target is None:
            return False
        if self._has_failure_evidence(state):
            return False

        meaningful = [
            token
            for token in tokens[1:]
            if token not in _STOP_WORDS and token not in _ACTION_VERBS
        ]
        if not meaningful:
            return False

        label = " ".join(
            re.findall(r"[a-z0-9]+", " ".join(
                part for part in (action.target.text, action.target.content_description) if part
            ).lower())
        )
        return all(term in label for term in meaningful)

    @staticmethod
    def _has_failure_evidence(state: WorldState | None) -> bool:
        if state is None:
            return False
        for element in state.elements:
            if element.clickable:
                continue
            text = " ".join(re.findall(r"[a-z0-9]+", element_text(element).lower()))
            if any(phrase in text for phrase in _FAILURE_PHRASES):
                return True
        return False

    def evaluate(self, goal: str, state: WorldState) -> bool:
        goal_norm = " ".join(re.findall(r"[a-z0-9]+", goal.lower()))
        if not goal_norm or self.is_action_goal(goal):
            return False

        labels = [" ".join(re.findall(r"[a-z0-9]+", element_text(e).lower())) for e in state.elements]
        meaningful = [t for t in re.findall(r"[a-z0-9]+", goal_norm) if t not in _STOP_WORDS and t not in _ACTION_VERBS]
        if not meaningful:
            return False
        return any(all(term in label for term in meaningful) for label in labels)
