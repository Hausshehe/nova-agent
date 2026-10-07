"""Bounded goal contracts for Nova's goal-driven autonomy phase."""

from __future__ import annotations

from dataclasses import dataclass


_MAX_TEXT = 512


@dataclass(frozen=True)
class GoalContract:
    """The explicit contract Nova must use to distinguish progress from completion."""

    goal: str
    success_condition: str
    status: str = "ACTIVE"

    def __post_init__(self) -> None:
        if not isinstance(self.goal, str) or not self.goal.strip():
            raise ValueError("Goal cannot be empty.")
        if not isinstance(self.success_condition, str) or not self.success_condition.strip():
            raise ValueError("Success condition cannot be empty.")
        if self.status not in {"ACTIVE", "VERIFIED", "FAILED"}:
            raise ValueError("Goal status must be ACTIVE, VERIFIED, or FAILED.")
        if len(self.goal.strip()) > _MAX_TEXT:
            raise ValueError("Goal is too long.")
        if len(self.success_condition.strip()) > _MAX_TEXT:
            raise ValueError("Success condition is too long.")

    def snapshot(self) -> dict[str, str]:
        return {
            "goal": self.goal.strip(),
            "success_condition": self.success_condition.strip(),
            "status": self.status,
        }


def establish_goal_contract(goal: str, success_condition: str) -> str:
    """Create one bounded goal contract without executing or changing device state."""
    contract = GoalContract(goal.strip(), success_condition.strip())
    return (
        "Goal contract established.\n"
        f"Goal: {contract.goal.strip()}\n"
        f"Success condition: {contract.success_condition.strip()}\n"
        f"Status: {contract.status}\n"
        "Safety boundary: this records the goal and its completion condition only; "
        "no action was executed and no device state was changed."
    )
