"""Explicit, evidence-aware semantic progress for Nova missions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ProgressStatus(str, Enum):
    """Current evidence-backed status of one meaningful goal requirement."""

    ACHIEVED = "achieved"
    CURRENT = "current"
    REMAINING = "remaining"
    UNCERTAIN = "uncertain"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class GoalRequirement:
    """One meaningful requirement of a mission, independent of UI actions."""

    id: str
    description: str

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("requirement id must not be empty")
        if not self.description.strip():
            raise ValueError("requirement description must not be empty")


@dataclass(frozen=True)
class RequirementProgress:
    """Evidence-backed state for one goal requirement."""

    requirement: GoalRequirement
    status: ProgressStatus = ProgressStatus.REMAINING
    evidence: tuple[str, ...] = ()

    def with_status(
        self,
        status: ProgressStatus,
        evidence: tuple[str, ...] = (),
    ) -> "RequirementProgress":
        return RequirementProgress(self.requirement, status, tuple(evidence))

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.requirement.id,
            "description": self.requirement.description,
            "status": self.status.value,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class SemanticProgress:
    """Bounded semantic mission progress; it records belief separately from proof."""

    requirements: tuple[RequirementProgress, ...] = ()

    def __post_init__(self) -> None:
        ids = [item.requirement.id for item in self.requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("requirement ids must be unique")

    @classmethod
    def from_requirements(
        cls,
        requirements: tuple[GoalRequirement, ...],
    ) -> "SemanticProgress":
        return cls(tuple(RequirementProgress(item) for item in requirements))

    def update(
        self,
        requirement_id: str,
        status: ProgressStatus,
        evidence: tuple[str, ...] = (),
    ) -> "SemanticProgress":
        found = False
        updated: list[RequirementProgress] = []
        for item in self.requirements:
            if item.requirement.id == requirement_id:
                updated.append(item.with_status(status, evidence))
                found = True
            else:
                updated.append(item)
        if not found:
            raise KeyError(f"unknown requirement: {requirement_id}")
        return SemanticProgress(tuple(updated))

    def snapshot(self) -> dict[str, Any]:
        grouped = {status.value: [] for status in ProgressStatus}
        for item in self.requirements:
            grouped[item.status.value].append(item.requirement.id)
        return {
            "requirements": [item.snapshot() for item in self.requirements],
            "achieved": grouped[ProgressStatus.ACHIEVED.value],
            "current": grouped[ProgressStatus.CURRENT.value],
            "remaining": grouped[ProgressStatus.REMAINING.value],
            "uncertain": grouped[ProgressStatus.UNCERTAIN.value],
            "blocked": grouped[ProgressStatus.BLOCKED.value],
        }
