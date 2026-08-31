from __future__ import annotations

import re
from typing import Any

from .core import Action, ActionType, Decision, Target
from .reasoning_context import ReasoningContext
from .targeting import _score


class DeterministicReasoner:
    """Small, explainable planner used as the stable baseline before any LLM."""

    @staticmethod
    def _meaningful_terms(goal: str) -> tuple[str, ...]:
        stop = {"a", "an", "the", "to", "of", "and", "then", "please", "tap", "click", "open"}
        return tuple(t for t in re.findall(r"[a-z0-9]+", goal.lower()) if t not in stop)

    @staticmethod
    def _used_ids(context: ReasoningContext) -> set[str]:
        return {
            str(item.get("target_id"))
            for item in context.history
            if item.get("target_id") is not None
        }

    def plan(self, context: ReasoningContext) -> Decision:
        candidates = [e for e in context.state.elements if e.enabled and e.clickable]
        if not candidates:
            raise RuntimeError("no clickable target available")

        used = self._used_ids(context)
        ranked = sorted(candidates, key=lambda e: _score(context.goal, e), reverse=True)

        # Recovery: after an accepted-but-unverified action, prefer another
        # matching target rather than blindly repeating the same node.
        for element in ranked:
            if element.id not in used and _score(context.goal, element) > 0:
                target = Target(element.id, element.text, element.content_description)
                return Decision(Action(ActionType.CLICK, target), f"selected matching target {element.id}")

        best = ranked[0]
        target = Target(best.id, best.text, best.content_description)
        return Decision(Action(ActionType.CLICK, target), f"reusing best matching target {best.id}")
