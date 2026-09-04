"""Deterministic reasoning for Nova Agent v2.

This module is intentionally small and local. It turns an explicit goal,
current observation, and completed attempt history into one auditable Decision.
It does not execute actions, poll Android, retry internally, or hide mutable
state.
"""

from __future__ import annotations

import re

from .models import Action, ActionType, Decision, UiElement
from .reasoning import ReasoningContext


_STOP_WORDS = frozenset(
    {
        "a", "an", "and", "at", "button", "for", "in", "me", "of",
        "on", "please", "the", "to",
    }
)


def _tokens(value: str) -> frozenset[str]:
    return frozenset(
        token
        for token in re.findall(r"[\w]+", value.casefold())
        if token not in _STOP_WORDS
    )


class DeterministicReasoner:
    """Choose a viable visible target without hidden recovery loops."""

    def decide(self, context: ReasoningContext) -> Decision:
        goal_tokens = _tokens(context.goal.text)
        if not goal_tokens:
            raise ValueError("goal contains no actionable tokens")

        attempted_ids = {
            step.decision.action.target_id
            for step in context.history
            if step.decision.action.type is ActionType.TAP
            and step.decision.action.target_id is not None
        }

        scored = [
            (self._score(goal_tokens, element), element)
            for element in context.observation.elements
            if self._is_viable(element)
        ]
        scored = [(score, element) for score, element in scored if score > 0]
        if not scored:
            raise ValueError("no visible enabled clickable element matches the goal")

        untried = [
            (score, element)
            for score, element in scored
            if element.id not in attempted_ids
        ]
        if not untried:
            raise ValueError("all matching targets have already been attempted")

        score, target = max(
            untried,
            key=lambda item: (
                item[0],
                -self._position(item[1], context.observation.elements),
            ),
        )
        label = target.text or target.content_description
        return Decision(
            action=Action(type=ActionType.TAP, target_id=target.id),
            reason=f"matched goal to visible target '{label}' with score {score}",
        )

    @staticmethod
    def _is_viable(element: UiElement) -> bool:
        return element.visible and element.enabled and element.clickable

    @staticmethod
    def _score(goal_tokens: frozenset[str], element: UiElement) -> int:
        label_tokens = _tokens(f"{element.text} {element.content_description}")
        overlap = len(goal_tokens & label_tokens)
        if overlap == 0:
            return 0
        exact = 2 if goal_tokens <= label_tokens else 0
        return overlap + exact

    @staticmethod
    def _position(element: UiElement, elements: tuple[UiElement, ...]) -> int:
        return elements.index(element)
