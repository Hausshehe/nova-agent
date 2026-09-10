"""Bounded cross-mission learning records for Nova Agent."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .mission_state import MissionState
from .models import RunResult


_RETRIEVAL_STOPWORDS = frozenset({
    "a", "an", "and", "for", "from", "in", "into", "of", "on", "or", "the", "to", "with",
    "change", "check", "close", "complete", "finish", "get", "go", "launch", "open", "start", "use",
})


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

    def retrieve(self, goal: str, max_results: int = 4) -> tuple[MissionLearningRecord, ...]:
        """Return the most relevant recent records using deterministic token overlap."""
        if not isinstance(goal, str) or not goal.strip():
            raise ValueError("goal must be a non-empty string")
        if max_results < 1:
            raise ValueError("max_results must be at least 1")

        goal_tokens = self._tokens(goal)
        if not goal_tokens:
            return ()

        ranked: list[tuple[float, int, MissionLearningRecord]] = []
        for index, record in enumerate(self.entries):
            record_tokens = self._tokens(record.goal)
            overlap = len(goal_tokens & record_tokens)
            if not overlap:
                continue
            # Prefer records that explain a larger share of their own goal.
            # This prevents a generic shared word from outranking a concise,
            # highly specific historical mission. Recent records still break
            # genuine score ties.
            specificity = overlap / len(record_tokens)
            ranked.append((specificity, index, record))

        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return tuple(record for _, _, record in ranked[:max_results])

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9]+", text.casefold())
            if len(token) > 1 and token not in _RETRIEVAL_STOPWORDS
        }
