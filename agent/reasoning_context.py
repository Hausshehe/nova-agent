from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .core import ActionType, Target, WorldState


@dataclass(frozen=True)
class ActionCandidate:
    """An explicit action the current UI makes available to the planner."""

    action_type: ActionType
    target: Target | None = None
    enabled: bool = True
    visible: bool = True
    class_name: str = ""
    bounds: str = ""
    editable: bool = False
    scrollable: bool = False
    checkable: bool = False
    checked: bool = False
    focused: bool = False


@dataclass(frozen=True)
class ReasoningContext:
    goal: str
    state: WorldState
    history: tuple[Mapping[str, Any], ...] = ()
    candidates: tuple[ActionCandidate, ...] = ()


def _build_candidates(state: WorldState) -> tuple[ActionCandidate, ...]:
    return tuple(
        ActionCandidate(
            action_type=ActionType.CLICK,
            target=Target(element.id, element.text, element.content_description),
            enabled=element.enabled,
            visible=element.visible,
            class_name=element.class_name,
            bounds=element.bounds,
            editable=element.editable,
            scrollable=element.scrollable,
            checkable=element.checkable,
            checked=element.checked,
            focused=element.focused,
        )
        for element in state.elements
        if element.clickable
    )


def build_reasoning_context(
    goal: str,
    state: WorldState,
    history: Sequence[Mapping[str, Any]],
) -> ReasoningContext:
    return ReasoningContext(
        goal=goal,
        state=state,
        history=tuple(history),
        candidates=_build_candidates(state),
    )
