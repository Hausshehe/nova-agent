"""Bounded goal-completion verification for Nova's 178 runtime loop."""

from __future__ import annotations

import re
from dataclasses import dataclass

_MAX_TEXT = 512
_MAX_EVIDENCE = 4096

_STOP_WORDS = {
    "a", "an", "and", "are", "be", "been", "being", "by", "current", "for",
    "is", "of", "on", "reported", "successfully", "the", "to", "was", "with",
}


@dataclass(frozen=True)
class GoalCompletionObservation:
    status: str
    reason: str

    def __post_init__(self) -> None:
        if self.status not in {"VERIFIED", "FAILED", "INCONCLUSIVE"}:
            raise ValueError("Goal completion status is invalid.")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("Goal completion reason cannot be empty.")


def _terms(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_]+", value.lower().replace("_", " "))
        if token not in _STOP_WORDS and len(token) > 2
    }


def _evidence_matches_clause(clause_terms: set[str], evidence_terms: set[str]) -> bool:
    if clause_terms & evidence_terms:
        return True
    for clause_term in clause_terms:
        for evidence_term in evidence_terms:
            if len(clause_term) >= 4 and len(evidence_term) >= 4 and (
                clause_term.startswith(evidence_term)
                or evidence_term.startswith(clause_term)
            ):
                return True
    return False


def verify_goal_completion(
    goal: str,
    success_condition: str,
    evidence: str,
) -> GoalCompletionObservation:
    """Verify the goal from evidence only; never execute or claim from tool success alone."""
    for value, label in (
        (goal, "Goal"),
        (success_condition, "Success condition"),
        (evidence, "Evidence"),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} cannot be empty.")
        if label == "Evidence":
            limit = _MAX_EVIDENCE
        else:
            limit = _MAX_TEXT
        if len(value.strip()) > limit:
            raise ValueError(f"{label} is too long.")

    normalized = evidence.strip()
    # Runtime contract-establishment/management text is not outcome evidence.
    # It can repeat the goal and success condition verbatim, which must never
    # be enough to verify the goal.
    evidence_lines = []
    for line in normalized.splitlines():
        stripped_line = line.strip()
        if (
            stripped_line.startswith("Runtime goal contract established for this turn.")
            or stripped_line.startswith("Goal:")
            or stripped_line.startswith("Success condition:")
            or stripped_line.startswith("The runtime state is ")
            or stripped_line.startswith("Any tool outcome must be observed as goal evidence;")
            or stripped_line.startswith("Observed tool:")
            or stripped_line.startswith("Observed recovery for:")
        ):
            continue
        evidence_lines.append(line)
    normalized = "\n".join(evidence_lines).strip()
    if not normalized:
        return GoalCompletionObservation(
            "INCONCLUSIVE",
            "Observed evidence contains only goal-management text, not a goal outcome.",
        )

    if re.search(
        r"\b(?:Outcome|Verification|Postcondition|Post-action verification)\s*:\s*FAILED\b"
        r"|\bTool error\s*:",
        normalized,
        re.IGNORECASE,
    ):
        return GoalCompletionObservation(
            "FAILED",
            "Observed evidence contains an explicit failure marker.",
        )

    condition_terms = _terms(success_condition)
    goal_terms = _terms(goal)
    evidence_terms = _terms(normalized)
    # Verify each conjunct of the success condition independently. The goal
    # may supply contextual wording, but a conjunct cannot be completed solely
    # because its terms already appeared in the goal. It needs observed terms
    # that establish that particular conjunct.
    clauses = [
        clause
        for clause in re.split(r"\band\b", success_condition, flags=re.IGNORECASE)
        if clause.strip()
    ]
    for clause in clauses:
        clause_terms = _terms(clause)
        if not clause_terms:
            continue
        if not _evidence_matches_clause(clause_terms, evidence_terms):
            return GoalCompletionObservation(
                "INCONCLUSIVE",
                "At least one success-condition clause has no observed evidence beyond wording already present in the goal.",
            )
    if condition_terms and condition_terms & evidence_terms:
        return GoalCompletionObservation(
            "VERIFIED",
            "Observed evidence establishes every success-condition clause with evidence beyond the goal wording.",
        )

    return GoalCompletionObservation(
        "INCONCLUSIVE",
        "Observed evidence does not fully establish the success condition.",
    )
