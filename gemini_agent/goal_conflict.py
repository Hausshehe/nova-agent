"""Bounded conflict resolution across Nova's active goal portfolio."""

from __future__ import annotations

from dataclasses import dataclass
import re

_MAX_TEXT = 512
_MAX_GOALS = 8


@dataclass(frozen=True)
class GoalConflictCandidate:
    goal_id: str
    goal: str
    conflict_key: str
    constraint: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.goal_id, "Goal id"),
            (self.goal, "Goal"),
            (self.conflict_key, "Conflict key"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} cannot be empty.")
            if len(value.strip()) > _MAX_TEXT:
                raise ValueError(f"{label} is too long.")
        if self.constraint not in {
            "MUST_CONTINUE",
            "CAN_DEFER",
            "MUST_NOT_INTERRUPT",
            "CAN_INTERRUPT",
        }:
            raise ValueError(
                "Constraint must be MUST_CONTINUE, CAN_DEFER, MUST_NOT_INTERRUPT, or CAN_INTERRUPT."
            )


def resolve_goal_conflicts(goals: str) -> str:
    """Resolve explicit multi-goal conflicts using compatibility constraints only."""
    if not isinstance(goals, str) or not goals.strip():
        raise ValueError("Goals cannot be empty.")
    entries = [entry.strip() for entry in re.split(r"[;\n]+", goals.strip()) if entry.strip()]
    if not entries or len(entries) > _MAX_GOALS:
        raise ValueError(f"Conflict resolution requires between 1 and {_MAX_GOALS} goals.")

    parsed: list[GoalConflictCandidate] = []
    seen: set[str] = set()
    for entry in entries:
        parts = [part.strip() for part in entry.split("|")]
        if len(parts) != 4:
            raise ValueError(
                "Each goal must use: goal_id | goal | conflict_key | constraint"
            )
        candidate = GoalConflictCandidate(parts[0], parts[1], parts[2], parts[3].upper())
        if candidate.goal_id in seen:
            raise ValueError("Goal ids must be unique.")
        seen.add(candidate.goal_id)
        parsed.append(candidate)

    groups: dict[str, list[GoalConflictCandidate]] = {}
    for candidate in parsed:
        groups.setdefault(candidate.conflict_key, []).append(candidate)

    lines = [
        "Goal conflict resolution (read-only):",
        f"Goal count: {len(parsed)}",
    ]
    conflict_count = 0
    unresolved = 0

    for conflict_key, group in groups.items():
        if len(group) < 2:
            continue
        conflict_count += 1
        lines.append(f"Conflict group: {conflict_key}")
        for candidate in group:
            lines.append(f"- {candidate.goal_id}: constraint={candidate.constraint}")

        must_continue = [g for g in group if g.constraint == "MUST_CONTINUE"]
        can_defer = [g for g in group if g.constraint == "CAN_DEFER"]
        must_not_interrupt = [g for g in group if g.constraint == "MUST_NOT_INTERRUPT"]
        can_interrupt = [g for g in group if g.constraint == "CAN_INTERRUPT"]

        if len(group) == 2 and must_continue and can_defer:
            winner, deferred = must_continue[0], can_defer[0]
            lines.extend([
                f"Resolution: {winner.goal_id} retains the conflicting resource/outcome; {deferred.goal_id} is safely deferrable.",
                f"Preservation: {deferred.goal_id} must retain its goal state and resume later; {winner.goal_id} must not silently invalidate it.",
            ])
        elif len(group) == 2 and must_not_interrupt and can_interrupt:
            protected, interruptible = must_not_interrupt[0], can_interrupt[0]
            lines.extend([
                f"Resolution: {protected.goal_id} retains uninterrupted ownership; {interruptible.goal_id} is safely deferrable.",
                f"Preservation: {interruptible.goal_id} must retain its goal state and resume later; {protected.goal_id} must not be interrupted by this conflict.",
            ])
        else:
            unresolved += 1
            lines.append(
                "Resolution: HUMAN INPUT REQUIRED because the supplied constraints do not establish a safe conflict resolution."
            )

    if conflict_count == 0:
        lines.append("Result: no competing goals share a conflict key.")
    elif unresolved == 0:
        lines.append("Result: all detected conflicts have a constraint-supported resolution.")
    else:
        lines.append(f"Result: {unresolved} conflict group(s) remain unresolved.")

    lines.extend([
        "Boundary: conflict resolution changes no goal state and executes no goal work.",
        "No device state was changed.",
    ])
    return "\n".join(lines)
