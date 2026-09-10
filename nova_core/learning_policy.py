"""Deterministic policy for safely applying cross-mission learning."""

from __future__ import annotations

from dataclasses import dataclass

from .learning_memory import MissionLearningRecord


@dataclass(frozen=True)
class LearningAssessment:
    """Bounded interpretation of historical learning for one current mission."""

    relevant: tuple[MissionLearningRecord, ...] = ()
    warnings: tuple[str, ...] = ()
    guidance: tuple[str, ...] = ()


class LearningApplicationPolicy:
    """Apply historical outcomes as evidence without allowing them to override reality."""

    _MAX_RECORDS = 4
    _MAX_WARNINGS = 8

    def assess(
        self,
        records: tuple[MissionLearningRecord, ...],
    ) -> LearningAssessment:
        if not isinstance(records, tuple):
            raise TypeError("records must be a tuple of MissionLearningRecord")
        if any(not isinstance(record, MissionLearningRecord) for record in records):
            raise TypeError("records must contain only MissionLearningRecord values")

        relevant = records[: self._MAX_RECORDS]
        warnings: list[str] = []
        for record in relevant:
            if record.status != "succeeded":
                warnings.append(
                    f"Historical mission failed: {record.goal}"
                    + (f" ({record.error})" if record.error else "")
                )
            for ineffective in record.ineffective_actions:
                action = ineffective.get("action", "unknown")
                target = ineffective.get("target")
                detail = f"{action} {target}" if target else str(action)
                warnings.append(
                    f"Historical action made no observable progress: {detail}"
                )
            if record.failed_actions:
                warnings.append(
                    f"Historical mission had {record.failed_actions} rejected action(s): {record.goal}"
                )

        guidance = (
            "Use historical learning as supporting evidence, not as proof that an action is valid now.",
            "The current observation has priority over every historical record.",
            "Do not repeat a historically ineffective action unless current evidence gives a concrete reason it may now work.",
            "Historical success may suggest a useful direction, but never authorizes an action by itself.",
        )
        return LearningAssessment(
            relevant=relevant,
            warnings=tuple(warnings[: self._MAX_WARNINGS]),
            guidance=guidance,
        )
