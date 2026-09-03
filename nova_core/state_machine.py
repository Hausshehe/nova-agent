"""Explicit, loop-free state transitions for Nova Agent v2."""

from __future__ import annotations

from enum import Enum


class RunState(str, Enum):
    CREATED = "created"
    OBSERVING = "observing"
    DECIDING = "deciding"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ABORTED = "aborted"


_TERMINAL_STATES = frozenset({RunState.SUCCEEDED, RunState.FAILED, RunState.ABORTED})

_ALLOWED_TRANSITIONS = {
    RunState.CREATED: frozenset({RunState.OBSERVING, RunState.ABORTED}),
    RunState.OBSERVING: frozenset({RunState.DECIDING, RunState.FAILED, RunState.ABORTED}),
    RunState.DECIDING: frozenset({RunState.EXECUTING, RunState.FAILED, RunState.ABORTED}),
    RunState.EXECUTING: frozenset({RunState.VERIFYING, RunState.FAILED, RunState.ABORTED}),
    RunState.VERIFYING: frozenset({RunState.OBSERVING, RunState.SUCCEEDED, RunState.FAILED, RunState.ABORTED}),
    RunState.SUCCEEDED: frozenset(),
    RunState.FAILED: frozenset(),
    RunState.ABORTED: frozenset(),
}


class InvalidTransition(ValueError):
    """Raised when a run attempts an illegal state transition."""


def transition(current: RunState, target: RunState) -> RunState:
    """Validate and return one explicit state transition.

    This function performs exactly one transition. It never retries, waits,
    polls, calls itself recursively, or executes runtime work.
    """
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise InvalidTransition(f"cannot transition from {current.value} to {target.value}")
    return target


def is_terminal(state: RunState) -> bool:
    """Return whether the state ends a run."""
    return state in _TERMINAL_STATES
