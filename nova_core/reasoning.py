from __future__ import annotations

from dataclasses import dataclass

from .mission_state import MissionState
from .models import Decision, ExecutionResult, Goal, Observation
from .planning import Plan


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
    mission_state: MissionState | None = None
    plan: Plan | None = None
