from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .core import Decision, WorldState
from .navigation import LegacyPlanner, _decide
from .reasoning_context import build_reasoning_context
from .reasoning_provider import ReasoningProvider


@dataclass
class RecoveryEngine:
    """Own recovery replanning after an action does not complete its transition."""

    recoveries: int = 0

    def reset(self) -> None:
        self.recoveries = 0

    def recover(
        self,
        goal: str,
        state: WorldState,
        history: Sequence[Mapping[str, Any]],
        planner: ReasoningProvider | LegacyPlanner,
    ) -> Decision:
        """Build a fresh context from the failed attempt and request a new decision."""
        self.recoveries += 1
        context = build_reasoning_context(goal, state, history)
        return _decide(planner, context)
