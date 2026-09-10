"""Bounded action-outcome memory for one Nova Agent mission."""

from __future__ import annotations

from dataclasses import dataclass

from .models import ActionType, ExecutionResult


@dataclass(frozen=True)
class ActionOutcome:
    """A compact factual record of one attempted action."""

    action_type: ActionType
    target_id: str | None
    target_label: str
    accepted: bool
    changed: bool
    error: str | None = None

    @classmethod
    def from_execution(
        cls,
        action_type: ActionType,
        target_id: str | None,
        target_label: str,
        result: ExecutionResult,
    ) -> "ActionOutcome":
        return cls(
            action_type=action_type,
            target_id=target_id,
            target_label=target_label,
            accepted=result.accepted,
            changed=result.changed,
            error=result.error,
        )

    def snapshot(self) -> dict[str, object]:
        return {
            "action": self.action_type.value,
            "target_id": self.target_id,
            "target_label": self.target_label or None,
            "accepted": self.accepted,
            "changed": self.changed,
            "error": self.error,
        }


@dataclass(frozen=True)
class OutcomeMemory:
    """Keep only the most recent factual action outcomes."""

    max_entries: int = 6
    entries: tuple[ActionOutcome, ...] = ()

    def __post_init__(self) -> None:
        if self.max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        if len(self.entries) > self.max_entries:
            raise ValueError("entries exceed max_entries")

    def remember(self, outcome: ActionOutcome) -> "OutcomeMemory":
        return OutcomeMemory(
            max_entries=self.max_entries,
            entries=(self.entries + (outcome,))[-self.max_entries :],
        )

    def snapshot(self) -> list[dict[str, object]]:
        return [entry.snapshot() for entry in self.entries]

    def ineffective_attempts(self, *, target_id: str | None = None) -> int:
        return sum(
            1
            for entry in self.entries
            if not entry.changed
            and (target_id is None or entry.target_id == target_id)
        )
