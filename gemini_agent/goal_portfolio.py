"""Bounded representation of multiple active goals for Nova's 184 multi-goal agency phase."""

from __future__ import annotations

from dataclasses import dataclass


_MAX_TEXT = 512
_MAX_GOALS = 8


@dataclass(frozen=True)
class PortfolioGoal:
    """One independently tracked goal inside a bounded goal portfolio."""

    goal_id: str
    goal: str
    success_condition: str
    status: str = "ACTIVE"

    def __post_init__(self) -> None:
        for value, label in (
            (self.goal_id, "Goal id"),
            (self.goal, "Goal"),
            (self.success_condition, "Success condition"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} cannot be empty.")
            if len(value.strip()) > _MAX_TEXT:
                raise ValueError(f"{label} is too long.")
        if self.status not in {"ACTIVE", "PAUSED", "VERIFIED", "FAILED", "ABANDONED"}:
            raise ValueError("Goal status is invalid.")

    def snapshot(self) -> dict[str, str]:
        return {
            "goal_id": self.goal_id.strip(),
            "goal": self.goal.strip(),
            "success_condition": self.success_condition.strip(),
            "status": self.status,
        }


@dataclass(frozen=True)
class GoalPortfolio:
    """Bounded collection of distinct goals without prioritizing or executing them."""

    goals: tuple[PortfolioGoal, ...]

    def __post_init__(self) -> None:
        if not self.goals:
            raise ValueError("Goal portfolio cannot be empty.")
        if len(self.goals) > _MAX_GOALS:
            raise ValueError(f"Goal portfolio cannot contain more than {_MAX_GOALS} goals.")
        ids = [goal.goal_id.strip() for goal in self.goals]
        if len(ids) != len(set(ids)):
            raise ValueError("Goal ids must be unique.")

    def snapshot(self) -> dict[str, object]:
        return {
            "goals": [goal.snapshot() for goal in self.goals],
            "count": len(self.goals),
        }


def establish_goal_portfolio(goals: str) -> str:
    """Represent multiple bounded goals without prioritizing, executing, or completing them.

    Each goal is supplied as:
        goal_id | goal | success_condition
    """
    if not isinstance(goals, str) or not goals.strip():
        raise ValueError("Goals cannot be empty.")

    entries = [line.strip() for line in goals.strip().splitlines() if line.strip()]
    if not entries:
        raise ValueError("Goal portfolio cannot be empty.")
    if len(entries) > _MAX_GOALS:
        raise ValueError(f"Goal portfolio cannot contain more than {_MAX_GOALS} goals.")

    parsed: list[PortfolioGoal] = []
    for entry in entries:
        parts = [part.strip() for part in entry.split("|")]
        if len(parts) != 3:
            raise ValueError("Each goal must use: goal_id | goal | success_condition")
        parsed.append(PortfolioGoal(*parts))

    portfolio = GoalPortfolio(tuple(parsed))
    lines = [
        "Goal portfolio established (read-only):",
        f"Goal count: {portfolio.snapshot()['count']}",
    ]
    for goal in portfolio.goals:
        lines.extend([
            f"- Goal id: {goal.goal_id.strip()}",
            f"  Goal: {goal.goal.strip()}",
            f"  Success condition: {goal.success_condition.strip()}",
            f"  Status: {goal.status}",
        ])
    lines.extend([
        "Boundary: goals are represented independently; no priority, execution, interruption, or completion decision was made.",
        "No action was executed and no device state was changed.",
    ])
    return "\n".join(lines)
