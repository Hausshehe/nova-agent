"""Small, dependency-free contracts for Nova Agent v2.

These models intentionally contain no execution, retry, polling, or planning
logic. Keeping data separate from behavior makes the control flow auditable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RunStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ABORTED = "aborted"


class ActionType(str, Enum):
    TAP = "tap"
    BACK = "back"
    SCROLL = "scroll"
    TYPE = "type"
    SWIPE = "swipe"
    WAIT = "wait"


@dataclass(frozen=True)
class Goal:
    text: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("goal must not be empty")


@dataclass(frozen=True)
class UiElement:
    id: str
    text: str = ""
    content_description: str = ""
    clickable: bool = False
    enabled: bool = True
    class_name: str = ""
    editable: bool = False
    scrollable: bool = False
    checkable: bool = False
    checked: bool = False
    focused: bool = False
    visible: bool = True


@dataclass(frozen=True)
class Observation:
    package: str
    activity: str
    elements: tuple[UiElement, ...] = ()
    revision: int = 0


@dataclass(frozen=True)
class Action:
    type: ActionType
    target_id: str | None = None
    value: str | None = None


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str = ""


@dataclass(frozen=True)
class ExecutionResult:
    accepted: bool
    changed: bool
    error: str | None = None


@dataclass(frozen=True)
class RunResult:
    status: RunStatus
    steps: int
    error: str | None = None
