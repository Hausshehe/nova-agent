from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Sequence

from .core import WorldState


@dataclass(frozen=True)
class AgentState:
    """Explicit runtime state carried between reasoning turns.

    This is deliberately small and serializable. It is the runtime's working
    state, not a transcript and not a permanent memory store.
    """

    goal: str
    world: WorldState
    step: int = 0
    status: str = "running"
    recent_history: tuple[Mapping[str, Any], ...] = ()
    failure_count: int = 0
    last_error: str | None = None
    plan: tuple[str, ...] = ()
    max_history: int = 8

    def record(
        self,
        event: Mapping[str, Any],
        *,
        world: WorldState | None = None,
        status: str | None = None,
        failure: bool = False,
        error: str | None = None,
        plan: Sequence[str] | None = None,
    ) -> "AgentState":
        history = (*self.recent_history, dict(event))[-self.max_history :]
        return replace(
            self,
            world=world if world is not None else self.world,
            step=self.step + 1,
            status=status if status is not None else self.status,
            recent_history=history,
            failure_count=self.failure_count + (1 if failure else 0),
            last_error=error,
            plan=tuple(plan) if plan is not None else self.plan,
        )

    def transition(
        self,
        *,
        world: WorldState | None = None,
        status: str | None = None,
        plan: Sequence[str] | None = None,
    ) -> "AgentState":
        return replace(
            self,
            world=world if world is not None else self.world,
            status=status if status is not None else self.status,
            plan=tuple(plan) if plan is not None else self.plan,
        )

    @property
    def history(self) -> tuple[Mapping[str, Any], ...]:
        """Compatibility/read-only alias for consumers that call it history."""
        return self.recent_history
