"""Bounded cross-mission learning records for Nova Agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .mission_state import MissionState
from .models import RunResult


@dataclass(frozen=True)
class MissionLearningRecord:
    """Factual summary of a completed mission that can be reused later."""

    goal: str
    status: str
    steps: int
    error: str | None = None
    changed_actions: int = 0
    failed_actions: int = 0
    ineffective_actions: tuple[dict[str, object], ...] = ()

    @classmethod
    def from_mission(cls, mission: MissionState, result: RunResult) -> "MissionLearningRecord":
        ineffective = tuple(
            outcome
            for outcome in mission.outcome_memory.snapshot()
            if outcome["accepted"] is True and outcome["changed"] is False
        )
        return cls(
            goal=mission.goal.text,
            status=result.status.value,
            steps=result.steps,
            error=result.error,
            changed_actions=mission.changed_actions,
            failed_actions=mission.failed_actions,
            ineffective_actions=ineffective,
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "status": self.status,
            "steps": self.steps,
            "error": self.error,
            "changed_actions": self.changed_actions,
            "failed_actions": self.failed_actions,
            "ineffective_actions": [dict(item) for item in self.ineffective_actions],
        }


@dataclass(frozen=True)
class LearningMemory:
    """Keep only a small, factual window of completed mission outcomes."""

    max_entries: int = 8
    entries: tuple[MissionLearningRecord, ...] = ()

    def __post_init__(self) -> None:
        if self.max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        if len(self.entries) > self.max_entries:
            raise ValueError("entries exceed max_entries")

    def remember(self, record: MissionLearningRecord) -> "LearningMemory":
        return LearningMemory(
            max_entries=self.max_entries,
            entries=(self.entries + (record,))[-self.max_entries :],
        )

    def snapshot(self) -> list[dict[str, Any]]:
        return [entry.snapshot() for entry in self.entries]
