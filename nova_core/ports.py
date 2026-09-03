"""Dependency-inversion ports for Nova Agent v2.

These protocols describe capabilities only. Implementations belong in runtime
adapters and must not leak Android, network, provider, retry, or orchestration
logic into the core.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import Action, ExecutionResult, Observation
from .models import Decision, Goal
from .reasoning import ReasoningContext


class Observer(Protocol):
    """Capability for obtaining the current UI observation."""

    def observe(self) -> Observation:
        ...


@runtime_checkable
class FreshObserver(Protocol):
    """Capability for obtaining an observation after a prior state changes."""

    def observe_fresh(self, previous: Observation) -> Observation:
        ...


class Reasoner(Protocol):
    """Capability for choosing one action from explicit run context."""

    def decide(self, context: ReasoningContext) -> Decision:
        ...


class Executor(Protocol):
    """Capability for attempting one action."""

    def execute(self, action: Action) -> ExecutionResult:
        ...


class Verifier(Protocol):
    """Capability for deciding whether one transition achieved the goal."""

    def verify(
        self,
        goal: Goal,
        before: Observation,
        decision: Decision,
        result: ExecutionResult,
        after: Observation,
    ) -> bool:
        ...
