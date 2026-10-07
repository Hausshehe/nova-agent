"""Bounded runtime state for Nova's 178 goal-driven autonomy loop."""

from __future__ import annotations

from dataclasses import dataclass, field


_MAX_TEXT = 512
_MAX_EVIDENCE = 8


@dataclass
class GoalState:
    """Track one goal contract and bounded evidence without claiming completion."""

    goal: str
    success_condition: str
    status: str = "ACTIVE"
    progress_status: str = "INCONCLUSIVE"
    progress_reason: str = "No goal-progress observation has been recorded."
    evidence: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.goal, str) or not self.goal.strip():
            raise ValueError("Goal cannot be empty.")
        if not isinstance(self.success_condition, str) or not self.success_condition.strip():
            raise ValueError("Success condition cannot be empty.")
        if self.status not in {"ACTIVE", "VERIFIED", "FAILED"}:
            raise ValueError("Goal status must be ACTIVE, VERIFIED, or FAILED.")
        if self.progress_status not in {"PROGRESS", "BLOCKED", "INCONCLUSIVE"}:
            raise ValueError("Goal progress status is invalid.")
        if not isinstance(self.progress_reason, str) or not self.progress_reason.strip():
            raise ValueError("Goal progress reason cannot be empty.")
        if len(self.goal.strip()) > _MAX_TEXT or len(self.success_condition.strip()) > _MAX_TEXT:
            raise ValueError("Goal contract text is too long.")

    def add_evidence(self, evidence: str) -> None:
        if not isinstance(evidence, str) or not evidence.strip():
            raise ValueError("Evidence cannot be empty.")
        self.evidence.append(evidence.strip()[:_MAX_TEXT])
        del self.evidence[:-_MAX_EVIDENCE]

    def snapshot(self) -> dict[str, object]:
        return {
            "goal": self.goal.strip(),
            "success_condition": self.success_condition.strip(),
            "status": self.status,
            "progress_status": self.progress_status,
            "progress_reason": self.progress_reason,
            "evidence": list(self.evidence),
        }


def start_goal_state(goal: str, success_condition: str) -> GoalState:
    """Create active runtime goal state; no execution or completion claim."""
    return GoalState(goal.strip(), success_condition.strip())
