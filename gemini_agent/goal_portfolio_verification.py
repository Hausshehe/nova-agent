"""Read-only verification of Nova's multi-goal portfolio coherence."""

from __future__ import annotations

from dataclasses import dataclass
import re

from gemini_agent.goal_completion import verify_goal_completion

_MAX_TEXT = 512
_MAX_EVIDENCE = 4096
_MAX_GOALS = 8
_VALID_STATUSES = {"ACTIVE", "PAUSED", "VERIFIED", "FAILED", "ABANDONED"}


@dataclass(frozen=True)
class PortfolioVerificationCandidate:
    goal_id: str
    goal: str
    success_condition: str
    status: str
    evidence: str

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
        if not isinstance(self.evidence, str) or not self.evidence.strip():
            raise ValueError("Evidence cannot be empty.")
        if len(self.evidence.strip()) > _MAX_EVIDENCE:
            raise ValueError("Evidence is too long.")
        if self.status not in _VALID_STATUSES:
            raise ValueError("Goal status is invalid.")


def verify_goal_portfolio(expected_goal_ids: str, goals: str) -> str:
    """Verify that a supplied goal portfolio remains complete and coherent."""
    if not isinstance(expected_goal_ids, str) or not expected_goal_ids.strip():
        raise ValueError("Expected goal ids cannot be empty.")
    if not isinstance(goals, str) or not goals.strip():
        raise ValueError("Goals cannot be empty.")

    expected = [item.strip() for item in expected_goal_ids.split(",") if item.strip()]
    if not expected or len(expected) > _MAX_GOALS:
        raise ValueError(f"Expected goal ids must contain between 1 and {_MAX_GOALS} ids.")
    if len(expected) != len(set(expected)):
        raise ValueError("Expected goal ids must be unique.")

    entries = [entry.strip() for entry in re.split(r"[;\n]+", goals.strip()) if entry.strip()]
    if not entries or len(entries) > _MAX_GOALS:
        raise ValueError(f"Portfolio verification requires between 1 and {_MAX_GOALS} goals.")

    parsed: list[PortfolioVerificationCandidate] = []
    seen: set[str] = set()
    goal_signatures: dict[str, str] = {}

    for entry in entries:
        parts = [part.strip() for part in entry.split("|")]
        if len(parts) != 5:
            raise ValueError(
                "Each goal must use: goal_id | goal | success_condition | status | evidence"
            )
        candidate = PortfolioVerificationCandidate(
            parts[0], parts[1], parts[2], parts[3].upper(), parts[4]
        )
        if candidate.goal_id in seen:
            raise ValueError("Goal ids must be unique.")
        seen.add(candidate.goal_id)
        signature = " ".join(candidate.goal.lower().split())
        if signature in goal_signatures:
            raise ValueError(
                f"Duplicate goal detected: {candidate.goal_id} duplicates {goal_signatures[signature]}."
            )
        goal_signatures[signature] = candidate.goal_id
        parsed.append(candidate)

    expected_set = set(expected)
    observed_set = set(seen)
    missing = [goal_id for goal_id in expected if goal_id not in observed_set]
    unexpected = [goal_id for goal_id in seen if goal_id not in expected_set]

    lines = [
        "Goal portfolio verification (read-only):",
        f"Expected goal count: {len(expected)}",
        f"Observed goal count: {len(parsed)}",
    ]

    if missing:
        lines.append("Missing goals: " + ", ".join(missing))
    else:
        lines.append("Missing goals: none")

    if unexpected:
        lines.append("Unexpected goals: " + ", ".join(unexpected))
    else:
        lines.append("Unexpected goals: none")

    incoherent: list[str] = []

    for candidate in parsed:
        completion = verify_goal_completion(
            candidate.goal,
            candidate.success_condition,
            candidate.evidence,
        )
        lines.extend([
            f"- {candidate.goal_id}: status={candidate.status}",
            f"  Evidence assessment: {completion.status}",
            f"  Evidence basis: {completion.reason}",
        ])

        if candidate.status == "VERIFIED" and completion.status != "VERIFIED":
            incoherent.append(
                f"{candidate.goal_id} is marked VERIFIED without verified success evidence"
            )
        elif candidate.status == "FAILED" and completion.status != "FAILED":
            incoherent.append(
                f"{candidate.goal_id} is marked FAILED without evidence supporting failure"
            )
        elif candidate.status in {"ACTIVE", "PAUSED"} and completion.status == "VERIFIED":
            incoherent.append(
                f"{candidate.goal_id} has verified success evidence but remains {candidate.status}"
            )
        elif candidate.status == "ABANDONED" and completion.status == "VERIFIED":
            incoherent.append(
                f"{candidate.goal_id} has verified success evidence but is marked ABANDONED"
            )

    if missing or unexpected:
        lines.append("Coherence: INCOHERENT because the expected and observed goal sets differ.")
    elif incoherent:
        lines.append("Coherence: INCOHERENT")
        for issue in incoherent:
            lines.append(f"- Issue: {issue}")
    else:
        lines.append("Coherence: VERIFIED")
        lines.append("All expected goals are present exactly once and their states agree with the supplied evidence.")

    lines.extend([
        "Boundary: verification is read-only; no goal state was changed and no goal work was executed.",
        "No device state was changed.",
    ])
    return "\n".join(lines)
