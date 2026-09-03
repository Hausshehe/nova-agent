from __future__ import annotations

import re
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


def _bounds(element: Any) -> tuple[int, int, int, int] | None:
    match = re.fullmatch(r"\[(\-?\d+),(\-?\d+)\]\[(\-?\d+),(\-?\d+)\]", element.bounds or "")
    if not match:
        return None
    return tuple(int(value) for value in match.groups())


def _intersects(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    left, top, right, bottom = a
    other_left, other_top, other_right, other_bottom = b
    return max(left, other_left) < min(right, other_right) and max(top, other_top) < min(bottom, other_bottom)


def _effectively_visible(element: Any, state: WorldState) -> bool:
    if not element.visible:
        return False
    element_bounds = _bounds(element)
    if element_bounds is None:
        return True
    viewports = [_bounds(item) for item in state.elements if item.scrollable and item.visible]
    viewports = [viewport for viewport in viewports if viewport is not None]
    if not viewports:
        return True
    return any(_intersects(element_bounds, viewport) for viewport in viewports)


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
            visible=True,
        )
        for element in state.elements
        if element.clickable and element.enabled and _effectively_visible(element, state)
    ]

    for element in state.elements:
        if element.scrollable and element.visible:
            candidates.append(
                ActionCandidate(
                    action_type=ActionType.SCROLL,
                    target=Target(element.id, element.text, element.content_description),
                    enabled=element.enabled,
                    visible=True,
                )
            )

    candidates.append(ActionCandidate(ActionType.BACK))
    return ReasoningContext(
        goal=goal,
        state=state,
        history=tuple(history),
        candidates=tuple(candidates),
    )
