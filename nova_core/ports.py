"""Dependency-inversion ports for Nova Agent v2.

These protocols describe capabilities only. Implementations belong in runtime
adapters and must not leak Android, network, provider, retry, or orchestration
logic into the core.
"""

from __future__ import annotations

from typing import Protocol

from .models import Action, Decision, ExecutionResult, Goal, Observation


class Observer(Protocol):
    """Capability for obtaining the current UI observation."""

    def observe(self) -> Observation:
        ...


class Reasoner(Protocol):
    """Capability for choosing one action for the current observation."""

    def decide(self, goal: Goal, observation: Observation) -> Decision:
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
