from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .core import WorldState


@dataclass(frozen=True)
class ReasoningContext:
    goal: str
    state: WorldState
    history: tuple[Mapping[str, Any], ...] = ()


def build_reasoning_context(
    goal: str,
    state: WorldState,
    history: Sequence[Mapping[str, Any]],
) -> ReasoningContext:
    return ReasoningContext(goal=goal, state=state, history=tuple(history))
