"""Deterministic reasoning for Nova Agent v2."""

from __future__ import annotations

import re

from .models import Action, ActionType, Decision, UiElement
from .reasoning import ReasoningContext

_STOP_WORDS = frozenset({
    "a", "an", "and", "at", "button", "for", "in", "me", "of", "on", "please", "the", "to",
})
_STATE_VERBS = frozenset({"open", "show", "display", "navigate", "go", "select", "choose"})
_TERMINAL_WORDS = frozenset({"finish", "complete", "completed", "done"})
_CONTINUE_WORDS = frozenset({"continue", "next", "proceed"})


def _tokens(value: str) -> frozenset[str]:
    return frozenset(token for token in re.findall(r"[\w]+", value.casefold()) if token not in _STOP_WORDS)


def _state_target_tokens(value: str) -> frozenset[str]:
    return frozenset(token for token in _tokens(value) if token not in _STATE_VERBS)


def _semantic_label_tokens(value: str) -> frozenset[str]:
    tokens = _tokens(value)
    return frozenset(token for token in tokens if token not in _STATE_VERBS)


def _started_step(observation_text: str) -> int | None:
    match = re.search(r"\bstep\s+(\d+)\s+started\b", observation_text.casefold())
    return int(match.group(1)) if match else None


class DeterministicReasoner:
    """Choose a viable visible target without hidden recovery loops."""

    def decide(self, context: ReasoningContext) -> Decision:
        goal_tokens = _tokens(context.goal.text)
        if not goal_tokens:
            raise ValueError("goal contains no actionable tokens")

        attempted_ids = {
            step.decision.action.target_id
            for step in context.history
            if step.decision.action.type is ActionType.TAP and step.decision.action.target_id is not None
        }

        state_tokens = _state_target_tokens(context.goal.text)
        if state_tokens != goal_tokens and state_tokens:
            scored = self._score_state_targets(state_tokens, context.observation.elements)
        else:
            scored = self._score_targets(goal_tokens, context.observation.elements)

        if not scored:
            raise ValueError("no visible enabled clickable element matches the goal")

        untried = [(score, element) for score, element in scored if element.id not in attempted_ids]
        if not untried:
            raise ValueError("all matching targets have already been attempted")

        untried = self._prefer_progression_action(context, goal_tokens, untried)
        score, target = max(untried, key=lambda item: (item[0], -self._position(item[1], context.observation.elements)))
        label = target.text or target.content_description
        return Decision(
            action=Action(type=ActionType.TAP, target_id=target.id),
            reason=f"matched goal to visible target '{label}' with score {score}",
        )

    @classmethod
    def _prefer_progression_action(
        cls,
        context: ReasoningContext,
        goal_tokens: frozenset[str],
        candidates: list[tuple[int, UiElement]],
    ) -> list[tuple[int, UiElement]]:
        """Prefer a visible continuation before a terminal action in a workflow."""
        if not goal_tokens & _TERMINAL_WORDS:
            return candidates

        visible_text = " ".join(
            f"{element.text} {element.content_description}"
            for element in context.observation.elements
            if element.visible
        )
        current_step = _started_step(visible_text)

        continuation = [
            item for item in candidates
            if _tokens(f"{item[1].text} {item[1].content_description}") & _CONTINUE_WORDS
        ]
        terminal = [
            item for item in candidates
            if _tokens(f"{item[1].text} {item[1].content_description}") & _TERMINAL_WORDS
        ]
        if not continuation or not terminal:
            return candidates

        if current_step is not None:
            if current_step < 2:
                return continuation
            return candidates

        completed_continuations = sum(
            1
            for step in context.history
            if step.decision.action.type is ActionType.TAP
            and step.decision.action.target_id is not None
            and _CONTINUE_WORDS
            & _tokens(f"{step.decision.action.target_id} {step.decision.reason}")
        )
        if completed_continuations == 0:
            return continuation
        return candidates

    @classmethod
    def _score_targets(cls, goal_tokens: frozenset[str], elements: tuple[UiElement, ...]) -> list[tuple[int, UiElement]]:
        scored = [(cls._score(goal_tokens, element), element) for element in elements if cls._is_viable(element)]
        return [(score, element) for score, element in scored if score > 0]

    @classmethod
    def _score_state_targets(cls, target_tokens: frozenset[str], elements: tuple[UiElement, ...]) -> list[tuple[int, UiElement]]:
        scored: list[tuple[int, UiElement]] = []
        for element in elements:
            if not cls._is_viable(element):
                continue
            label_tokens = _semantic_label_tokens(f"{element.text} {element.content_description}")
            if label_tokens != target_tokens:
                continue
            score = len(target_tokens) + 2
            if _tokens(f"{element.text} {element.content_description}") == target_tokens:
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
