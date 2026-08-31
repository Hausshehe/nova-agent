from __future__ import annotations

import re

from .core import WorldState, element_text


class GoalEvaluator:
    """Conservative goal completion checks based on the current UI state."""

    def evaluate(self, goal: str, state: WorldState) -> bool:
        goal_norm = " ".join(re.findall(r"[a-z0-9]+", goal.lower()))
        if not goal_norm:
            return False

        labels = [" ".join(re.findall(r"[a-z0-9]+", element_text(e).lower())) for e in state.elements]
        # A goal is considered complete when its meaningful final phrase is
        # represented by visible UI text. This deliberately avoids accepting
        # an action merely because the action call itself succeeded.
        meaningful = [t for t in re.findall(r"[a-z0-9]+", goal_norm) if t not in {"a", "an", "the", "to", "of", "and", "then", "please", "tap", "click", "open"}]
        if not meaningful:
            return False
        return any(all(term in label for term in meaningful) for label in labels)
