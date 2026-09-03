from __future__ import annotations

import re
from difflib import SequenceMatcher

from .core import Action, ActionType, Decision
from .reasoning_context import ActionCandidate, ReasoningContext


class DeterministicReasoner:
    """Small, explainable reasoning provider used as Nova's stable baseline."""

    @staticmethod
    def _meaningful_terms(goal: str) -> tuple[str, ...]:
        stop = {"a", "an", "the", "to", "of", "and", "then", "please", "tap", "click", "open"}
        return tuple(t for t in re.findall(r"[a-z0-9]+", goal.lower()) if t not in stop)

    @staticmethod
    def _used_ids(context: ReasoningContext) -> set[str]:
        return {str(item.get("target_id")) for item in context.history if item.get("target_id") is not None}

    @staticmethod
    def _score(goal: str, candidate: ActionCandidate) -> float:
        if candidate.target is None:
            return 0.0
        goal_tokens = set(re.findall(r"[a-z0-9]+", goal.lower()))
        label = " ".join(part for part in (candidate.target.text, candidate.target.content_description) if part).strip()
        label_tokens = set(re.findall(r"[a-z0-9]+", label.lower()))
        if not goal_tokens or not label_tokens:
            return 0.0
        overlap = len(goal_tokens & label_tokens) / len(goal_tokens)
        if overlap == 0:
            return 0.0
        ratio = SequenceMatcher(None, goal.lower(), label.lower()).ratio()
        exact = 1.0 if goal.strip().lower() == label.strip().lower() else 0.0
        return exact * 10.0 + overlap * 4.0 + ratio

    @staticmethod
    def _global_action(context: ReasoningContext) -> Decision | None:
        terms = set(DeterministicReasoner._meaningful_terms(context.goal))
        if "back" in terms:
            for candidate in context.candidates:
                if candidate.action_type is ActionType.BACK and candidate.enabled and candidate.visible:
                    return Decision(Action(ActionType.BACK), "goal explicitly requests back")
        if "wait" in terms or "waits" in terms:
            for candidate in context.candidates:
                if candidate.action_type is ActionType.WAIT and candidate.enabled and candidate.visible:
                    return Decision(Action(ActionType.WAIT), "goal explicitly requests wait")
        return None

    def decide(self, context: ReasoningContext) -> Decision:
        global_action = self._global_action(context)
        if global_action is not None:
            return global_action

        visible_clicks = [
            candidate for candidate in context.candidates
            if candidate.action_type is ActionType.CLICK
            and candidate.enabled and candidate.visible and candidate.target is not None
        ]
        used = self._used_ids(context)
        ranked = sorted(visible_clicks, key=lambda c: self._score(context.goal, c), reverse=True)

        for candidate in ranked:
            if candidate.target.element_id not in used and self._score(context.goal, candidate) > 0:
                target = candidate.target
                return Decision(Action(ActionType.CLICK, target), f"selected matching target {target.element_id}")

        hidden_goal = any(
            candidate.action_type is ActionType.CLICK
            and candidate.enabled
            and not candidate.visible
            and candidate.target is not None
            and self._score(context.goal, candidate) > 0
            for candidate in context.candidates
        )
        if hidden_goal:
            for candidate in context.candidates:
                if candidate.action_type is ActionType.SCROLL and candidate.enabled and candidate.visible and candidate.target:
                    return Decision(Action(ActionType.SCROLL, candidate.target), "scroll toward an off-screen goal candidate")

        if not ranked:
            raise RuntimeError("no clickable target available")

        best = ranked[0]
        target = best.target
        return Decision(Action(ActionType.CLICK, target), f"reusing best matching target {target.element_id}")

    def plan(self, context: ReasoningContext) -> Decision:
        """Backward-compatible planner entry point for the existing kernel."""
        return self.decide(context)
