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
_STATE_VERBS = frozenset({"open", "show", "display", "navigate", "go", "select", "choose"})


def _tokens(value: str) -> frozenset[str]:
    return frozenset(
        token
        for token in re.findall(r"[\w]+", value.casefold())
        if token not in _STOP_WORDS
    )


def _state_target_tokens(value: str) -> frozenset[str]:
    tokens = _tokens(value)
    return frozenset(token for token in tokens if token not in _STATE_VERBS)


def _semantic_label_tokens(value: str) -> frozenset[str]:
    """Return label tokens after removing state intent words.

    This lets a control labelled ``Open Settings`` satisfy the target
    ``Settings`` while preventing a generic partial match such as
    ``Test Navigation Action`` from being treated as the ``Navigation``
    destination.
    """
    tokens = _tokens(value)
    return frozenset(token for token in tokens if token not in _STATE_VERBS)


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

        state_tokens = _state_target_tokens(context.goal.text)
        if state_tokens != goal_tokens and state_tokens:
            scored = self._score_state_targets(state_tokens, context.observation.elements)
        else:
            scored = self._score_targets(goal_tokens, context.observation.elements)

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

    @classmethod
    def _score_targets(
        cls, goal_tokens: frozenset[str], elements: tuple[UiElement, ...]
    ) -> list[tuple[int, UiElement]]:
        scored = [
            (cls._score(goal_tokens, element), element)
            for element in elements
            if cls._is_viable(element)
        ]
        return [(score, element) for score, element in scored if score > 0]

    @classmethod
    def _score_state_targets(
        cls, target_tokens: frozenset[str], elements: tuple[UiElement, ...]
    ) -> list[tuple[int, UiElement]]:
        """Select a direct visible target for a state-transition goal.

        State verbs such as ``open`` or ``navigate`` describe the intended
        outcome, not necessarily the label of the control that initiates it.
        A candidate is accepted only when its meaningful label exactly matches
        the requested target. This prevents related but different controls
        such as ``Test Navigation Action`` from being selected for ``Open
        Navigation`` merely because they share one token.
        """
        scored: list[tuple[int, UiElement]] = []
        for element in elements:
            if not cls._is_viable(element):
                continue
            label_tokens = _semantic_label_tokens(
                f"{element.text} {element.content_description}"
            )
            if label_tokens != target_tokens:
                continue

            score = len(target_tokens) + 2
            raw_label_tokens = _tokens(f"{element.text} {element.content_description}")
            if raw_label_tokens == target_tokens:
                score += 1
            scored.append((score, element))
        return scored

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
