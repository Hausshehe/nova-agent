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
    terms = {
        token
        for token in re.findall(r"[a-z0-9_]+", value.lower().replace("_", " "))
        if token not in _STOP_WORDS and len(token) > 2
    }
    # ISO-8601 date/datetime output is substantive evidence even when the
    # tool result contains only the timestamp and no literal "date" word.
    if re.search(r"\b\d{4}-\d{2}-\d{2}(?:[tT ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:[zZ]|[+-]\d{2}:?\d{2})?)?\b", value):
        terms.add("date")
    return terms


def _evidence_matches_clause(
    clause_terms: set[str],
    evidence_terms: set[str],
    context_terms: set[str] | None = None,
) -> bool:
    """Match a clause using observed evidence plus goal context, but require observation."""
    context_terms = context_terms or set()
    observed = 0
    for clause_term in clause_terms:
        if clause_term in evidence_terms:
            observed += 1
            continue
        if any(
            len(clause_term) >= 4
            and len(evidence_term) >= 4
            and (
                clause_term.startswith(evidence_term)
                or evidence_term.startswith(clause_term)
            )
            for evidence_term in evidence_terms
        ):
            observed += 1
            continue
        if clause_term in context_terms:
            continue
        return False
    return observed > 0


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

    failure_marker = bool(
        re.search(
            r"\b(?:Outcome|Verification|Postcondition|Post-action verification)\s*:\s*FAILED\b"
            r"|\bTool error\s*:",
            normalized,
            re.IGNORECASE,
        )
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
    ordered_clause_seen = False
    for clause in clauses:
        clause_terms = _terms(clause)
        if not clause_terms:
            continue
        ordered_parts = re.split(
            r"\b(?:after|before|then)\b",
            clause,
            flags=re.IGNORECASE,
        )
        if len(ordered_parts) > 1:
            ordered_clause_seen = True
            for part in ordered_parts:
                part_terms = _terms(part)
                if part_terms and not _evidence_matches_clause(
                    part_terms,
                    evidence_terms,
                    goal_terms,
                ):
                    if failure_marker:
                        return GoalCompletionObservation(
                            "INCONCLUSIVE",
                            "An ordered success-condition requirement lacks observed evidence; an explicit failed prerequisite does not by itself fail the overall goal.",
                        )
                    return GoalCompletionObservation(
                        "INCONCLUSIVE",
                        "At least one ordered success-condition requirement lacks its own observed evidence.",
                    )
            continue
        if not _evidence_matches_clause(clause_terms, evidence_terms, goal_terms):
            if failure_marker:
                return GoalCompletionObservation(
                    "FAILED",
                    "Observed evidence contains an explicit failure marker and the success-condition clause is not established.",
                )
            return GoalCompletionObservation(
                "INCONCLUSIVE",
                "At least one success-condition clause has no observed evidence beyond wording already present in the goal.",
            )
    if failure_marker and not ordered_clause_seen:
        return GoalCompletionObservation(
            "FAILED",
            "Observed evidence contains an explicit failure marker.",
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
