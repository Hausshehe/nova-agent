"""Bounded goal-progress observation for Nova's 178 runtime loop."""

from __future__ import annotations

import re
from dataclasses import dataclass

_MAX_TEXT = 512

_STOP_WORDS = {
    "a", "an", "and", "are", "be", "been", "being", "by", "current", "for",
    "is", "of", "on", "reported", "successfully", "the", "to", "was", "with",
}


@dataclass(frozen=True)
class GoalProgressObservation:
    status: str
    reason: str

    def __post_init__(self) -> None:
        if self.status not in {"PROGRESS", "BLOCKED", "INCONCLUSIVE"}:
            raise ValueError("Goal progress status is invalid.")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("Goal progress reason cannot be empty.")


def _terms(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_]+", value.lower())
        if token not in _STOP_WORDS and len(token) > 2
    }


def observe_goal_progress(
    goal: str,
    success_condition: str,
    evidence: str,
) -> GoalProgressObservation:
    """Classify observed evidence without claiming final goal completion."""
    for value, label in (
        (goal, "Goal"),
        (success_condition, "Success condition"),
        (evidence, "Evidence"),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} cannot be empty.")
        if len(value.strip()) > _MAX_TEXT:
            raise ValueError(f"{label} is too long.")

    normalized = evidence.strip()
    if re.search(
        r"\b(?:Outcome|Verification|Postcondition|Post-action verification)\s*:\s*FAILED\b"
        r"|\bTool error\s*:",
        normalized,
        re.IGNORECASE,
    ):
        return GoalProgressObservation(
            "BLOCKED",
            "Observed evidence contains an explicit failure marker.",
        )

    condition_terms = _terms(success_condition)
    evidence_terms = _terms(normalized)
    overlap = condition_terms & evidence_terms
    if condition_terms and len(overlap) >= max(1, (len(condition_terms) + 1) // 2):
        return GoalProgressObservation(
            "PROGRESS",
            "Observed evidence overlaps the success condition without claiming final completion.",
        )

    return GoalProgressObservation(
        "INCONCLUSIVE",
        "Observed evidence does not provide bounded evidence of goal progress.",
    )
