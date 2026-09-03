from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .core import ActionType, Target, WorldState


@dataclass(frozen=True)
class ActionCandidate:
    action_type: ActionType
    target: Target | None = None
    enabled: bool = True
    visible: bool = True


@dataclass(frozen=True)
class ReasoningContext:
    goal: str
    state: WorldState
    history: tuple[Mapping[str, Any], ...] = ()
    candidates: tuple[ActionCandidate, ...] = ()


def build_reasoning_context(
    goal: str,
    state: WorldState,
    history: Sequence[Mapping[str, Any]],
) -> ReasoningContext:
    candidates = [
        ActionCandidate(
            action_type=ActionType.CLICK,
            target=Target(element.id, element.text, element.content_description),
            enabled=element.enabled,
            visible=element.visible,
        )
        for element in state.elements
        if element.clickable and element.visible
    ]
    candidates.extend(
        ActionCandidate(
            action_type=ActionType.SCROLL,
            target=Target(element.id, element.text, element.content_description),
            enabled=element.enabled,
            visible=element.visible,
        )
        for element in state.elements
        if element.scrollable and element.visible
    )
    candidates.append(ActionCandidate(ActionType.BACK))
    candidates.append(ActionCandidate(ActionType.WAIT))
    return ReasoningContext(
        goal=goal,
        state=state,
        history=tuple(history),
        candidates=tuple(candidates),
    )
