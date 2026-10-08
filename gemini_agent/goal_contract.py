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


@dataclass(frozen=True)
class OutcomeContract:
    """Define the observable transition and evidence needed to prove a goal outcome."""

    goal: str
    success_condition: str
    expected_transition: str
    observable_evidence: str
    failure_condition: str
    uncertainty: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.goal, "Goal"),
            (self.success_condition, "Success condition"),
            (self.expected_transition, "Expected transition"),
            (self.observable_evidence, "Observable evidence"),
            (self.failure_condition, "Failure condition"),
            (self.uncertainty, "Uncertainty"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} cannot be empty.")
            if len(value.strip()) > _MAX_TEXT:
                raise ValueError(f"{label} is too long.")

    def snapshot(self) -> dict[str, str]:
        return {
            "goal": self.goal.strip(),
            "success_condition": self.success_condition.strip(),
            "expected_transition": self.expected_transition.strip(),
            "observable_evidence": self.observable_evidence.strip(),
            "failure_condition": self.failure_condition.strip(),
            "uncertainty": self.uncertainty.strip(),
        }


def establish_outcome_contract(
    goal: str,
    success_condition: str,
    expected_transition: str,
    observable_evidence: str,
    failure_condition: str,
    uncertainty: str,
) -> str:
    """Create a bounded outcome contract without executing or changing state."""
    contract = OutcomeContract(
        goal.strip(),
        success_condition.strip(),
        expected_transition.strip(),
        observable_evidence.strip(),
        failure_condition.strip(),
        uncertainty.strip(),
    )
    return (
        "Outcome contract established (read-only).\\n"
        f"Goal: {contract.goal.strip()}\\n"
        f"Success condition: {contract.success_condition.strip()}\\n"
        f"Expected transition: {contract.expected_transition.strip()}\\n"
        f"Observable evidence: {contract.observable_evidence.strip()}\\n"
        f"Failure condition: {contract.failure_condition.strip()}\\n"
        f"Uncertainty: {contract.uncertainty.strip()}\\n"
        "Safety boundary: this defines the intended outcome and its evidence only; "
        "no action was executed and no device state was changed."
    )


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
