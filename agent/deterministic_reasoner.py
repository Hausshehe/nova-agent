from __future__ import annotations

import re
from typing import Any

from .core import Action, ActionType, Decision, Target
from .reasoning_context import ActionCandidate, ReasoningContext
from .targeting import _score


class DeterministicReasoner:
    """Small, explainable planner used as a stable fallback before any LLM."""

    _PREREQUISITE_WORDS = ("start", "begin", "initialize", "select", "choose", "enable")

    @staticmethod
    def _meaningful_terms(goal: str) -> tuple[str, ...]:
        stop = {"a", "an", "the", "to", "of", "and", "then", "please", "tap", "click", "open"}
        return tuple(t for t in re.findall(r"[a-z0-9]+", goal.lower()) if t not in stop)

    @staticmethod
    def _used_ids(context: ReasoningContext) -> set[str]:
        return {
            str(item.get("target_id"))
            for item in context.history
            if item.get("target_id") is not None and item.get("task_effect") != "blocked"
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

    @staticmethod
    def _latest_blocked_target(context: ReasoningContext) -> str | None:
        for item in reversed(context.history):
            if item.get("task_effect") == "blocked":
                target_id = item.get("target_id")
                return str(target_id) if target_id is not None else None
        return None

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
        blocker = self._latest_blocked_target(context)
        blocker_evidence = next(
            (str(item.get("effect_evidence") or "").lower() for item in reversed(context.history) if item.get("task_effect") == "blocked"),
            "",
        )

        # If the UI says a prerequisite must happen first, walk backward from
        # the blocked target and choose the earliest unused semantic candidate.
        # This uses current UI structure, not knowledge of a particular app.
        if "first" in blocker_evidence and blocker:
            element_ids = [element.id for element in context.state.elements]
            try:
                blocked_index = element_ids.index(blocker)
            except ValueError:
                blocked_index = len(element_ids)
            for element in context.state.elements[:blocked_index]:
                if not element.clickable or not element.enabled or element.id in used:
                    continue
                candidate = next(
                    (item for item in ranked if item.target.element_id == element.id),
                    None,
                )
                if candidate is not None and self._target_score(context, candidate) > 0:
                    return Decision(
                        Action(ActionType.CLICK, candidate.target),
                        f"selected prerequisite candidate {candidate.target.element_id}",
                    )

        # Do not immediately retry the last blocked target while another new
        # semantic action is available. Once the alternatives are exhausted,
        # the previously blocked target becomes eligible after state progress.
        fresh_matches = [
            candidate
            for candidate in ranked
            if candidate.target.element_id not in used
            and candidate.target.element_id != blocker
            and self._target_score(context, candidate) > 0
        ]
        if fresh_matches:
            candidate = fresh_matches[0]
            return Decision(
                Action(ActionType.CLICK, candidate.target),
                f"selected matching target {candidate.target.element_id}",
            )

        if blocker:
            blocked_candidate = next(
                (candidate for candidate in ranked if candidate.target.element_id == blocker),
                None,
            )
            if blocked_candidate is not None and self._target_score(context, blocked_candidate) > 0:
                return Decision(
                    Action(ActionType.CLICK, blocked_candidate.target),
                    f"revisiting previously blocked target {blocked_candidate.target.element_id} after progress",
                )

        # If no visible click is a new semantic match, use a visible scroll
        # candidate rather than inventing an off-screen target or stale node.
        for candidate in candidates:
            if candidate.action_type is ActionType.SCROLL:
                return Decision(Action(ActionType.SCROLL, candidate.target), "scroll to reveal more of the current UI")

        if ranked:
            best = ranked[0]
            return Decision(Action(ActionType.CLICK, best.target), f"reusing best matching target {best.target.element_id}")

        raise RuntimeError("no click or scroll candidate available")
