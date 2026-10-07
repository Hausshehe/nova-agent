"""Bounded next-step selection for Nova's 178 goal loop."""

from __future__ import annotations

import re
from dataclasses import dataclass

_MAX_TEXT = 512
_MAX_CANDIDATES = 32
_STOP_WORDS = {
    "a","an","and","are","be","been","being","by","current","for","from",
    "is","of","on","reported","successfully","the","to","was","with",
}

@dataclass(frozen=True)
class GoalNextStep:
    action: str
    reason: str

    def __post_init__(self) -> None:
        if self.action != "STOP" and not self.action.strip():
            raise ValueError("Next-step action cannot be empty.")
        if self.action == "STOP" and not self.reason.strip():
            raise ValueError("STOP requires a reason.")

def _terms(value: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9_]+", value.lower())
        if token not in _STOP_WORDS and len(token) > 2
    }

def select_goal_next_step(
    goal: str,
    success_condition: str,
    progress_status: str,
    progress_reason: str,
    candidates: list[str],
) -> GoalNextStep:
    """Select one bounded next action without executing it."""
    for value, label in (
        (goal, "Goal"),
        (success_condition, "Success condition"),
        (progress_reason, "Progress reason"),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} cannot be empty.")
        if len(value.strip()) > _MAX_TEXT:
            raise ValueError(f"{label} is too long.")
    if progress_status not in {"PROGRESS", "BLOCKED", "INCONCLUSIVE"}:
        raise ValueError("Progress status is invalid.")
    if not isinstance(candidates, list) or not candidates or len(candidates) > _MAX_CANDIDATES:
        raise ValueError("Candidates must contain between 1 and 32 items.")

    clean = []
    for candidate in candidates:
        if not isinstance(candidate, str) or not candidate.strip() or len(candidate.strip()) > _MAX_TEXT:
            raise ValueError("Each candidate must be bounded non-empty text.")
        clean.append(candidate.strip())

    if progress_status == "VERIFIED":
        return GoalNextStep(
            "STOP",
            "The goal is already verified; no further action is justified.",
        )

    goal_terms = _terms(goal)
    condition_terms = _terms(success_condition)
    target_terms = goal_terms | condition_terms

    scored = []
    for index, candidate in enumerate(clean):
        candidate_terms = _terms(candidate)
        score = len(candidate_terms & target_terms)
        if progress_status == "BLOCKED" and re.search(r"recover|retry|diagnos|repair|replan", candidate, re.I):
            score += 3
        scored.append((score, -index, candidate))

    best_score, _, best = max(scored)
    if best_score <= 0:
        return GoalNextStep(
            "STOP",
            "No candidate has a bounded semantic connection to the active goal.",
        )
    return GoalNextStep(
        best,
        f"Selected the candidate with the strongest bounded relevance to the active goal ({best_score} relevance points).",
    )
