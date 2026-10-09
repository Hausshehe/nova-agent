"""Bounded next-step selection for Nova's 178 goal loop."""

from __future__ import annotations

import re
from dataclasses import dataclass

_MAX_TEXT = 512
_MAX_CANDIDATES = 256
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
        raise ValueError("Candidates must contain between 1 and 256 items.")
    clean = []
    for candidate in candidates:
        if not isinstance(candidate, str) or not candidate.strip() or len(candidate.strip()) > _MAX_TEXT:
            raise ValueError("Each candidate must be bounded non-empty text.")
        clean.append(candidate.strip())
    if goal_status == "VERIFIED":
        return GoalNextStep("STOP", "The goal is already verified; no further action is justified.")
    if goal_status == "FAILED":
        return GoalNextStep("STOP", "The goal is failed; no bounded next action is justified from the supplied state.")

    # Construction goals need an action-capable path, not lexical matches to
    # orchestration tools such as build_intent_clarification or list_directory.
    # The constructed-action executor can inspect the environment first and then
    # create/build artifacts; repeatedly selecting planning/observation helpers
    # without excluding prior actions caused the live goal loop to stall.
    construction_request = re.search(
        r"\b(?:build|create|construct|generate|implement|make)\b",
        f"{goal} {success_condition}",
        re.IGNORECASE,
    )
    if construction_request and progress_status == "BLOCKED":
        # A failed construction action must be diagnosed before another attempt.
        # Otherwise the generic construction preference masks recovery candidates
        # and can repeat the same invalid executable indefinitely.
        for diagnostic in (
            "diagnose_command_failure",
            "diagnose_outcome_discrepancy",
            "diagnose_android_mechanism_outcome",
            "diagnose_capability_failure",
        ):
            if diagnostic in clean:
                return GoalNextStep(
                    diagnostic,
                    "The previous construction action is blocked; diagnose its recorded failure before retrying."
                )
    if construction_request and "execute_constructed_action" in clean and progress_status != "BLOCKED":
        return GoalNextStep(
            "execute_constructed_action",
            "A construction goal requires an action-capable path; use the bounded "
            "constructed-action executor to inspect prerequisites and make concrete progress."
        )

    goal_terms = _terms(goal)
    condition_terms = _terms(success_condition)
    observed_terms = _terms(evidence)
    remaining_condition_terms = condition_terms - observed_terms
    remaining_goal_terms = goal_terms - observed_terms
    target_terms = remaining_condition_terms | remaining_goal_terms

    # When the success condition expresses an ordering dependency such as
    # "X after Y", prefer the capability that can establish Y before the
    # capability that can establish X.
    prerequisite_terms: set[str] = set()
    after_match = re.search(r"\bafter\s+(.+)$", success_condition, re.IGNORECASE)
    if after_match:
        prerequisite_terms = _terms(after_match.group(1))

    scored = []
    for index, candidate in enumerate(clean):
        candidate_terms = _terms(candidate)
        score = len(candidate_terms & target_terms)
        if prerequisite_terms and candidate_terms & prerequisite_terms:
            score += 4
        # Treat bounded lexical extensions such as "datetime" -> "date"
        # as related evidence without introducing domain-specific aliases.
        for candidate_term in candidate_terms:
            for target_term in target_terms:
                if len(target_term) >= 4 and len(candidate_term) >= 4 and (
                    candidate_term.startswith(target_term)
                    or target_term.startswith(candidate_term)
                ):
                    score += 1
        if progress_status == "BLOCKED" and re.search(r"recover|retry|diagnos|repair|replan", candidate, re.I):
            score += 3
        # Verification-only actions must not outrank a still-unattempted primary
        # action merely because both share a broad term such as "command".
        # Verification is useful after execution evidence exists, not as a
        # substitute for the action required by the goal.
        if progress_status != "BLOCKED" and not observed_terms and re.search(
            r"\bverify(?:_|\b)|\bverification\b", candidate, re.I
        ):
            score -= 3
        # Recovery actions are justified by an observed blocked/failure state,
        # not merely by the fact that the goal mentions recovery-related words.
        # Prefer attempting the primary action while the goal is still unblocked.
        if progress_status != "BLOCKED" and not re.search(
            r"\b(?:failed|failure|error|blocked|recovery)\b",
            evidence,
            re.I,
        ) and re.search(r"(?:recover|retry|diagnos|repair|replan)", candidate, re.I):
            score -= 3
        scored.append((score, -index, candidate))
    best_score, _, best = max(scored)
    if best_score <= 0:
        if (
            "execute_constructed_action" in clean
            and re.search(r"\b(?:build|create|construct|generate|implement|make|write)\b", f"{goal} {success_condition}", re.IGNORECASE)
        ):
            return GoalNextStep(
                "execute_constructed_action",
                "No predefined capability has sufficient semantic relevance; "
                "use the generic constructed-action executor to perform the next "
                "bounded workspace action required by the goal."
            )
        return GoalNextStep("STOP", "No candidate has a bounded semantic connection to the remaining active goal.")
    reason = "Selected the candidate with the strongest bounded relevance to the active goal"
    if evidence.strip() and remaining_condition_terms:
        reason += " and its remaining success-condition evidence"
    return GoalNextStep(best, f"{reason} ({best_score} relevance points).")
