from __future__ import annotations

import re

from .core import WorldState, element_text


_ACTION_VERBS = {"tap", "click", "open"}
_STOP_WORDS = {"a", "an", "the", "to", "of", "and", "then", "please"}


class GoalEvaluator:
    """Conservative goal completion checks based on the current UI state."""

    def is_action_goal(self, goal: str) -> bool:
        tokens = re.findall(r"[a-z0-9]+", goal.lower())
        return bool(tokens) and tokens[0] in _ACTION_VERBS

    def evaluate(self, goal: str, state: WorldState) -> bool:
        goal_norm = " ".join(re.findall(r"[a-z0-9]+", goal.lower()))
        if not goal_norm or self.is_action_goal(goal):
            return False

        labels = [" ".join(re.findall(r"[a-z0-9]+", element_text(e).lower())) for e in state.elements]
        meaningful = [t for t in re.findall(r"[a-z0-9]+", goal_norm) if t not in _STOP_WORDS and t not in _ACTION_VERBS]
        if not meaningful:
            return False
        return any(all(term in label for term in meaningful) for label in labels)
