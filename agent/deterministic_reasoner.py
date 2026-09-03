from __future__ import annotations

import re
from typing import Any

from .core import Action, ActionType, Decision, Target
from .reasoning_context import ActionCandidate, ReasoningContext
from .targeting import _score


class DeterministicReasoner:
    """Small, explainable planner used as a stable fallback before any LLM."""

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

    @staticmethod
    def _target_score(context: ReasoningContext, candidate: ActionCandidate) -> float:
        if candidate.target is None:
            return 0.0
        element = next(
            (element for element in context.state.elements if element.id == candidate.target.element_id),
            None,
        )
        return _score(context.goal, element) if element is not None else 0.0

    def plan(self, context: ReasoningContext) -> Decision:
        candidates = [
            candidate
            for candidate in context.candidates
            if candidate.enabled and candidate.visible and candidate.target is not None
        ]
        if not candidates:
            raise RuntimeError("no actionable candidate available")

        used = self._used_ids(context)
        clicks = [candidate for candidate in candidates if candidate.action_type is ActionType.CLICK]
        ranked = sorted(clicks, key=lambda candidate: self._target_score(context, candidate), reverse=True)

        # Recovery: after an accepted-but-blocked action, prefer another
        # currently available matching target instead of repeating the same node.
        for candidate in ranked:
            score = self._target_score(context, candidate)
            if candidate.target.element_id not in used and score > 0:
                return Decision(
                    Action(ActionType.CLICK, candidate.target),
                    f"selected matching target {candidate.target.element_id}",
                )

        # If no visible click is a new semantic match, use a visible scroll
        # candidate rather than inventing an off-screen target or clicking a
        # stale node. The runtime will observe again before the next decision.
        for candidate in candidates:
            if candidate.action_type is ActionType.SCROLL:
                return Decision(Action(ActionType.SCROLL, candidate.target), "scroll to reveal more of the current UI")

        if ranked:
            best = ranked[0]
            return Decision(Action(ActionType.CLICK, best.target), f"reusing best matching target {best.target.element_id}")

        raise RuntimeError("no click or scroll candidate available")
