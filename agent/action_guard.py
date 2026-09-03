from __future__ import annotations

from dataclasses import dataclass

from .core import Action, WorldState
from .task_state import TaskState


@dataclass(frozen=True)
class ActionGuardResult:
    """Decision from the mechanical execution boundary."""

    allowed: bool
    reason: str = ""
    evidence: str = ""


class ActionGuard:
    """Prevent actions that task evidence says are blocked in the current state."""

    def check(self, action: Action, state: WorldState, task_state: TaskState) -> ActionGuardResult:
        constraints = task_state.active_constraints(state)
        for constraint in constraints:
            if constraint.matches(action):
                return ActionGuardResult(
                    allowed=False,
                    reason=constraint.reason,
                    evidence=constraint.evidence,
                )
        return ActionGuardResult(allowed=True)
