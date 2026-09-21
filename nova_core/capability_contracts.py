"""Explicit data contracts for Nova's AI capabilities.

These contracts separate capability semantics from provider selection. Providers may
differ, but a capability must expose one stable request/response shape to the core.
No provider, network, Android, retry, or orchestration details belong here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .models import Decision, ExecutionResult, Goal, Observation
from .planning import Plan
from .reasoning import ReasoningContext


class VerificationStatus(str, Enum):
    """Outcome reported by a verification capability."""

    VERIFIED = "verified"
    PROGRESS = "progress"
    NO_PROGRESS = "no_progress"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ReasoningRequest:
    """Context supplied to a reasoning capability."""

    context: ReasoningContext


@dataclass(frozen=True)
class ReasoningResponse:
    """Provider-neutral result of mission-level reasoning."""

    decision: Decision
    rationale: str = ""


@dataclass(frozen=True)
class PlanningRequest:
    """Context supplied to the mission-planning capability."""

    context: ReasoningContext


@dataclass(frozen=True)
class PlanningResponse:
    """Provider-neutral mission plan returned by planning."""

    plan: Plan

@dataclass(frozen=True)
class ActionSelectionRequest:
    """Context supplied when selecting exactly one executable action."""

    context: ReasoningContext


@dataclass(frozen=True)
class ActionSelectionResponse:
    """Provider-neutral result of action selection."""

    decision: Decision


@dataclass(frozen=True)
class PerceptionRequest:
    """Current Android evidence supplied to a perception capability."""

    observation: Observation


@dataclass(frozen=True)
class PerceptionResponse:
    """Structured world-state result produced by perception."""

    observation: Observation
    summary: str = ""


@dataclass(frozen=True)
class VerificationRequest:
    """Before/after evidence supplied to a verification capability."""

    goal: Goal
    before: Observation
    decision: Decision
    execution: ExecutionResult
    after: Observation


@dataclass(frozen=True)
class VerificationResponse:
    """Provider-neutral assessment of whether the mission advanced."""

    status: VerificationStatus
    evidence: tuple[str, ...] = ()
    confidence: float | None = None

    def __post_init__(self) -> None:
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("verification confidence must be between 0 and 1")
