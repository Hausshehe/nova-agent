from __future__ import annotations

from dataclasses import dataclass

from .models import Decision, ExecutionResult, Goal, Observation


@dataclass(frozen=True)
class ReasoningStep:
    decision: Decision
    execution: ExecutionResult
    post_observation: Observation | None = None


@dataclass(frozen=True)
class ReasoningContext:
    goal: Goal
    observation: Observation
    history: tuple[ReasoningStep, ...] = ()
    evidence: object | None = None
