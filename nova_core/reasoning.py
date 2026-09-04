"""Reasoning contracts for Nova Agent v2.

Reasoning is deliberately given explicit run context. Recovery decisions must
be able to see what was attempted, whether it changed the UI, and what the UI
became afterward, without hiding mutable state inside a provider.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Decision, ExecutionResult, Goal, Observation


@dataclass(frozen=True)
class ReasoningStep:
    """One completed decision/execution pair and its resulting observation."""

    decision: Decision
    execution: ExecutionResult
    post_observation: Observation | None = None


@dataclass(frozen=True)
class ReasoningContext:
    """Complete read-only context supplied to one reasoning decision."""

    goal: Goal
    observation: Observation
    history: tuple[ReasoningStep, ...] = ()
