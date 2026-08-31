from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ActionKind(str, Enum):
    """Actions understood by the rebuilt Nova task layer.

    These are intent-level operations. Android-specific execution stays behind
    a separate executor so the reasoner does not become coupled to transport
    details or one UI automation implementation.
    """

    OPEN_APP = "open_app"
    LAUNCH_PACKAGE = "launch_package"
    CLICK = "click"
    CLICK_AT = "click_at"
    TYPE = "type"
    PRESS_ENTER = "press_enter"
    PRESS_BACK = "press_back"
    PRESS_HOME = "press_home"
    SCROLL = "scroll"
    SWIPE = "swipe"
    WAIT = "wait"
    READ_SCREEN = "read_screen"
    DONE = "done"


@dataclass(frozen=True)
class AgentAction:
    """A serializable intent emitted by a planner/reasoner."""

    kind: ActionKind
    params: Mapping[str, Any] = field(default_factory=dict)
    rationale: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "params", dict(self.params))

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.kind.value,
            "params": dict(self.params),
            "reasoning": self.rationale,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AgentAction":
        raw_kind = str(payload.get("action", "")).strip().lower()
        try:
            kind = ActionKind(raw_kind)
        except ValueError as exc:
            raise ValueError(f"unsupported action: {raw_kind!r}") from exc

        raw_params = payload.get("params", {})
        if raw_params is None:
            raw_params = {}
        if not isinstance(raw_params, Mapping):
            raise TypeError("action params must be a mapping")

        rationale = payload.get("reasoning", "")
        if rationale is None:
            rationale = ""
        if not isinstance(rationale, str):
            raise TypeError("action reasoning must be a string")

        return cls(kind=kind, params=raw_params, rationale=rationale)
