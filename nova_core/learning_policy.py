"""Deterministic policy for safely applying cross-mission learning."""

from __future__ import annotations

from dataclasses import dataclass

from .learning_memory import MissionLearningRecord, MissionLesson


@dataclass(frozen=True)
class LearningAssessment:
    """Bounded interpretation of historical learning for one current mission."""

    relevant: tuple[MissionLearningRecord, ...] = ()
    lessons: tuple[MissionLesson, ...] = ()
    warnings: tuple[str, ...] = ()
    guidance: tuple[str, ...] = ()


class LearningApplicationPolicy:
    """Apply historical outcomes as evidence without allowing them to override reality."""

    _MAX_RECORDS = 4
    _MAX_WARNINGS = 8
    _MAX_LESSONS = 4

    def assess(
        self,
        records: tuple[MissionLearningRecord, ...],
        *,
        goal: str | None = None,
    ) -> LearningAssessment:
        if not isinstance(records, tuple):
            raise TypeError("records must be a tuple of MissionLearningRecord")
        if any(not isinstance(record, MissionLearningRecord) for record in records):
            raise TypeError("records must contain only MissionLearningRecord values")
        if goal is not None and (not isinstance(goal, str) or not goal.strip()):
            raise ValueError("goal must be a non-empty string when provided")

        relevant = records[: self._MAX_RECORDS]
        lessons = ()
        if goal is not None:
            lessons = LearningMemoryView(relevant).extract_lessons(goal, self._MAX_LESSONS)

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
        if lessons:
            guidance = guidance + tuple(lesson.guidance for lesson in lessons)
        return LearningAssessment(
            relevant=relevant,
            lessons=lessons,
            warnings=tuple(warnings[: self._MAX_WARNINGS]),
            guidance=guidance,
        )


class LearningMemoryView:
    """Small adapter used when policy already has only the relevant records."""

    def __init__(self, records: tuple[MissionLearningRecord, ...]) -> None:
        self._records = records

    def extract_lessons(self, goal: str, max_results: int) -> tuple[MissionLesson, ...]:
        from .learning_memory import LearningMemory

        return LearningMemory(entries=self._records).extract_lessons(goal, max_results)
