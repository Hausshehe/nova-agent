"""Deterministic uncertainty assessment for Nova Agent missions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UncertaintyAssessment:
    """Bounded statement of what the runtime knows and does not know."""

    level: str
    basis: str
    unknowns: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()

    def snapshot(self) -> dict[str, object]:
        return {
            "level": self.level,
            "basis": self.basis,
            "unknowns": list(self.unknowns),
            "conflicts": list(self.conflicts),
        }
