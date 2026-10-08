"""Bounded priority selection across Nova's active goal portfolio."""

from __future__ import annotations

from dataclasses import dataclass
import re

_MAX_TEXT = 512
_MAX_GOALS = 8


@dataclass(frozen=True)
class GoalPriorityCandidate:
    goal_id: str
    goal: str
    urgency: int = 0
    user_priority: int = 0
    dependency_count: int = 0
    resource_cost: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.goal_id, str) or not self.goal_id.strip():
            raise ValueError("Goal id cannot be empty.")
        if not isinstance(self.goal, str) or not self.goal.strip():
            raise ValueError("Goal cannot be empty.")
        if len(self.goal_id.strip()) > _MAX_TEXT or len(self.goal.strip()) > _MAX_TEXT:
            raise ValueError("Goal text is too long.")
        for value, label in (
            (self.urgency, "Urgency"),
            (self.user_priority, "User priority"),
            (self.dependency_count, "Dependency count"),
            (self.resource_cost, "Resource cost"),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 100:
                raise ValueError(f"{label} must be an integer from 0 to 100.")

    def score(self) -> int:
        return (self.user_priority * 1_000_000) + (self.urgency * 10_000) + (self.dependency_count * 100) - self.resource_cost


@dataclass(frozen=True)
class GoalPriorityDecision:
    selected_goal_id: str
    reason: str
    score: int

    def __post_init__(self) -> None:
        if not self.selected_goal_id.strip():
            raise ValueError("Selected goal id cannot be empty.")
        if not self.reason.strip():
            raise ValueError("Priority reason cannot be empty.")


def select_goal_priority(goals: str) -> str:
    """Select one goal for attention without executing, modifying, or completing goals.

    Each goal is supplied as:
        goal_id | goal | urgency | user_priority | dependency_count | resource_cost
    All numeric signals are explicit and bounded 0-100.
    """
    if not isinstance(goals, str) or not goals.strip():
        raise ValueError("Goals cannot be empty.")
    entries = [entry.strip() for entry in re.split(r"[;\n]+", goals.strip()) if entry.strip()]
    if not entries or len(entries) > _MAX_GOALS:
        raise ValueError(f"Priority selection requires between 1 and {_MAX_GOALS} goals.")

    parsed: list[GoalPriorityCandidate] = []
    seen: set[str] = set()
    for entry in entries:
        parts = [part.strip() for part in entry.split("|")]
        if len(parts) != 6:
            raise ValueError(
                "Each goal must use: goal_id | goal | urgency | user_priority | dependency_count | resource_cost"
            )
        try:
            values = [int(value) for value in parts[2:]]
        except ValueError as exc:
            raise ValueError("Priority signals must be integers from 0 to 100.") from exc
        candidate = GoalPriorityCandidate(parts[0], parts[1], *values)
        if candidate.goal_id in seen:
            raise ValueError("Goal ids must be unique.")
        seen.add(candidate.goal_id)
        parsed.append(candidate)

    ranked = sorted(parsed, key=lambda item: (-item.score(), item.goal_id))
    selected = ranked[0]
    tied = [item for item in ranked if item.score() == selected.score()]
    if len(tied) > 1:
        return (
            "Goal priority assessment (read-only):\n"
            "Decision: HUMAN INPUT REQUIRED\n"
            "Reason: multiple goals have the same highest priority score; no unsupported tie-breaker was invented.\n"
            f"Highest score: {selected.score()}\n"
            f"Tied goals: {', '.join(item.goal_id for item in tied)}\n"
            "No action was executed and no goal state was changed."
        )

    decision = GoalPriorityDecision(
        selected.goal_id,
        "Selected from explicit user-priority, urgency, dependency, and resource-cost signals.",
        selected.score(),
    )
    lines = [
        "Goal priority assessment (read-only):",
        f"Selected goal: {decision.selected_goal_id}",
        f"Priority score: {decision.score}",
        f"Reason: {decision.reason}",
        "Boundary: this selects which goal deserves attention; it does not execute, interrupt, complete, or modify any goal.",
        "No action was executed and no goal state was changed.",
    ]
    return "\n".join(lines)
