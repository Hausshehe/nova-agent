"""Bounded next-step selection for Nova's 178 goal loop."""

from __future__ import annotations

import re
from dataclasses import dataclass

_MAX_TEXT = 512
_MAX_CANDIDATES = 128
_STOP_WORDS = {
    "a","an","and","are","be","been","being","by","current","for","from",
    "is","of","on","reported","successfully","the","to","was","with","get","status","system",
}

@dataclass(frozen=True)
class GoalNextStep:
    action: str
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.action, str) or not self.action.strip():
            raise ValueError("Next-step action cannot be empty.")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("Next-step reason cannot be empty.")

def _terms(value: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+", value.lower().replace("_", " "))
        if token not in _STOP_WORDS and len(token) > 2
    }

def select_goal_next_step(
    goal: str,
    success_condition: str,
    goal_status: str,
    progress_status: str,
    progress_reason: str,
    candidates: list[str],
    evidence: str = "",
) -> GoalNextStep:
    """Select one bounded next action without executing it."""
    for value, label in (
        (goal, "Goal"),
        (success_condition, "Success condition"),
        (progress_reason, "Progress reason"),
        (evidence, "Evidence"),
    ):
        if not isinstance(value, str):
            raise ValueError(f"{label} must be text.")
        if len(value.strip()) > _MAX_TEXT:
            raise ValueError(f"{label} is too long.")
    if not str(goal).strip():
        raise ValueError("Goal cannot be empty.")
    if not str(success_condition).strip():
        raise ValueError("Success condition cannot be empty.")
    if not str(progress_reason).strip():
        raise ValueError("Progress reason cannot be empty.")
    if goal_status not in {"ACTIVE", "VERIFIED", "FAILED"}:
        raise ValueError("Goal status is invalid.")
    if progress_status not in {"PROGRESS", "BLOCKED", "INCONCLUSIVE"}:
        raise ValueError("Progress status is invalid.")
    if not isinstance(candidates, list) or not candidates or len(candidates) > _MAX_CANDIDATES:
        raise ValueError("Candidates must contain between 1 and 128 items.")
    clean = []
    for candidate in candidates:
        if not isinstance(candidate, str) or not candidate.strip() or len(candidate.strip()) > _MAX_TEXT:
            raise ValueError("Each candidate must be bounded non-empty text.")
        clean.append(candidate.strip())
    if goal_status == "VERIFIED":
        return GoalNextStep("STOP", "The goal is already verified; no further action is justified.")
    if goal_status == "FAILED":
        return GoalNextStep("STOP", "The goal is failed; no bounded next action is justified from the supplied state.")

    goal_terms = _terms(goal)
    condition_terms = _terms(success_condition)
    observed_terms = _terms(evidence)
    remaining_condition_terms = condition_terms - observed_terms
    remaining_goal_terms = goal_terms - observed_terms
    target_terms = remaining_condition_terms | remaining_goal_terms

    scored = []
    for index, candidate in enumerate(clean):
        candidate_terms = _terms(candidate)
        score = len(candidate_terms & target_terms)
        # Treat bounded lexical extensions such as "datetime" -> "date"
        # as related evidence without introducing domain-specific aliases.
        for candidate_term in candidate_terms:
            for target_term in target_terms:
                if len(target_term) >= 4 and len(candidate_term) >= 4 and (
                    candidate_term.startswith(target_term)
                    or target_term.startswith(candidate_term)
                    or target_term in candidate_term
                    or candidate_term in target_term
                ):
                    score += 1
        if progress_status == "BLOCKED" and re.search(r"recover|retry|diagnos|repair|replan", candidate, re.I):
            score += 3
        scored.append((score, -index, candidate))
    best_score, _, best = max(scored)
    if best_score <= 0:
        return GoalNextStep("STOP", "No candidate has a bounded semantic connection to the remaining active goal.")
    reason = "Selected the candidate with the strongest bounded relevance to the active goal"
    if evidence.strip() and remaining_condition_terms:
        reason += " and its remaining success-condition evidence"
    return GoalNextStep(best, f"{reason} ({best_score} relevance points).")
