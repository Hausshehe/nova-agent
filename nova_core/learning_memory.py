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
class MissionLesson:
    """A reusable lesson distilled only from repeated factual mission outcomes."""

    trigger_tokens: tuple[str, ...]
    action: str
    target: str | None
    outcome: str
    occurrences: int
    confidence: str

    def snapshot(self) -> dict[str, Any]:
        return {
            "trigger_tokens": list(self.trigger_tokens),
            "action": self.action,
            "target": self.target,
            "outcome": self.outcome,
            "occurrences": self.occurrences,
            "confidence": self.confidence,
        }

    @property
    def guidance(self) -> str:
        target = f" '{self.target}'" if self.target else ""
        return (
            f"For goals sharing {', '.join(self.trigger_tokens)}, action {self.action}{target} "
            f"was historically ineffective ({self.occurrences} occurrence(s)). "
            "Treat this as a warning, not a prohibition."
        )


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
            specificity = overlap / len(record_tokens)
            ranked.append((specificity, index, record))

        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return tuple(record for _, _, record in ranked[:max_results])

    def extract_lessons(self, goal: str, max_results: int = 4) -> tuple[MissionLesson, ...]:
        """Distill repeated ineffective actions into bounded, reusable warnings.

        A lesson is emitted only when the same action/target pattern appears in
        relevant historical missions. A single failure remains a raw record,
        preventing Nova from turning one bad experience into a permanent rule.
        """
        if not isinstance(goal, str) or not goal.strip():
            raise ValueError("goal must be a non-empty string")
        if max_results < 1:
            raise ValueError("max_results must be at least 1")

        goal_tokens = self._tokens(goal)
        if not goal_tokens:
            return ()

        patterns: dict[tuple[tuple[str, ...], str, str | None], int] = {}
        for record in self.entries:
            record_tokens = self._tokens(record.goal)
            overlap = goal_tokens & record_tokens
            if not overlap:
                continue
            trigger = tuple(sorted(overlap))
            for ineffective in record.ineffective_actions:
                action = str(ineffective.get("action", "unknown"))
                target_value = ineffective.get("target")
                target = str(target_value) if target_value else None
                key = (trigger, action, target)
                patterns[key] = patterns.get(key, 0) + 1

        lessons: list[MissionLesson] = []
        for (trigger, action, target), occurrences in patterns.items():
            if occurrences < 2:
                continue
            confidence = "high" if occurrences >= 3 else "medium"
            lessons.append(
                MissionLesson(
                    trigger_tokens=trigger,
                    action=action,
                    target=target,
                    outcome="ineffective",
                    occurrences=occurrences,
                    confidence=confidence,
                )
            )

        lessons.sort(key=lambda lesson: (lesson.occurrences, len(lesson.trigger_tokens)), reverse=True)
        return tuple(lessons[:max_results])

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9]+", text.casefold())
            if len(token) > 1 and token not in _RETRIEVAL_STOPWORDS
        }
