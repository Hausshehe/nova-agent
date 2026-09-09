"""Bounded, provider-neutral planning primitives for Nova Agent v2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .reasoning import ReasoningContext


_MAX_PLAN_STEPS = 8


@dataclass(frozen=True)
class PlanStep:
    """One bounded intent in a mission plan, not a concrete UI action."""

    description: str


@dataclass(frozen=True)
class Plan:
    """A bounded sequence of intents proposed for the current mission."""

    steps: tuple[PlanStep, ...]
    revision: int = 0
    cursor: int = 0

    def __post_init__(self) -> None:
        if not self.steps:
            raise ValueError("plan must contain at least one step")
        if len(self.steps) > _MAX_PLAN_STEPS:
            raise ValueError(f"plan must contain at most {_MAX_PLAN_STEPS} steps")
        if self.cursor < 0 or self.cursor > len(self.steps):
            raise ValueError("plan cursor is out of range")

    @property
    def current(self) -> PlanStep | None:
        return self.steps[self.cursor] if self.cursor < len(self.steps) else None

    @property
    def remaining(self) -> tuple[PlanStep, ...]:
        return self.steps[self.cursor :]

    @property
    def complete(self) -> bool:
        return self.cursor >= len(self.steps)

    def advance(self) -> "Plan":
        if self.complete:
            return self
        return Plan(self.steps, revision=self.revision, cursor=self.cursor + 1)


class Planner(Protocol):
    """Capability for creating and replacing a bounded mission plan."""

    def plan(self, context: ReasoningContext) -> Plan:
        ...

    def replan(self, context: ReasoningContext, previous: Plan) -> Plan:
        ...


class GoalPlanner:
    """Minimal safe planner used when no model-backed planner is configured.

    It deliberately does not decompose arbitrary natural language.
    The plan is one intent, leaving concrete action selection to the reasoner.
    """

    def plan(self, context: ReasoningContext) -> Plan:
        return Plan((PlanStep(context.goal.text),), revision=0)

    def replan(self, context: ReasoningContext, previous: Plan) -> Plan:
        return Plan((PlanStep(context.goal.text),), revision=previous.revision + 1)
