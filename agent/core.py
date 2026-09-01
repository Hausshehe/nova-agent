from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


class ActionType(str, Enum):
    CLICK = "click"
    BACK = "back"
    WAIT = "wait"


@dataclass(frozen=True)
class UIElement:
    id: str
    text: str = ""
    content_description: str = ""
    clickable: bool = False
    enabled: bool = True
    class_name: str = ""
    bounds: str = ""
    editable: bool = False
    scrollable: bool = False
    checkable: bool = False
    checked: bool = False
    focused: bool = False
    visible: bool = True


@dataclass(frozen=True)
class WorldState:
    package: str = ""
    activity: str = ""
    elements: tuple[UIElement, ...] = ()
    observation_id: str = ""
    timestamp_ms: int = 0


@dataclass(frozen=True)
class Target:
    element_id: str
    text: str = ""
    content_description: str = ""


@dataclass(frozen=True)
class Action:
    type: ActionType
    target: Target | None = None


@dataclass(frozen=True)
class Decision:
    action: Action
    rationale: str = ""


@dataclass(frozen=True)
class ExecutionResult:
    accepted: bool
    changed: bool
    verified: bool = False
    error: str | None = None


@dataclass(frozen=True)
class TransitionVerifier:
    def verify(self, before: WorldState, after: WorldState, result: ExecutionResult) -> bool:
        if not result.accepted:
            return False
        if not result.changed:
            return False
        return before != after


def element_text(element: UIElement) -> str:
    return " ".join(p for p in (element.text, element.content_description) if p).strip()


def normalize_history(history: Sequence[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    return tuple(history)
