"""Generic evidence extraction for bounded Nova Agent v2 reasoning."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Observation
from .reasoning import ReasoningStep


_STAGE_WORDS = {"start": 10, "begin": 10, "launch": 10, "continue": 20, "next": 20, "proceed": 20, "finish": 30, "complete": 30, "done": 30, "submit": 40}
_BLOCKING_PATTERNS = (
    re.compile(r"^(?P<required>.+?)\s+first(?:\b|$)", re.IGNORECASE),
    re.compile(r"^(?P<required>.+?)\s+(?:must|needs to|need to)\s+be\s+.+$", re.IGNORECASE),
    re.compile(r"^(?P<required>.+?)\s+before\s+.+$", re.IGNORECASE),
)


@dataclass(frozen=True)
class StateEvidence:
    """Evidence available to a reasoner; fields are observations, not beliefs."""
    current_revision: int
    previous_revision: int | None
    visible_labels: tuple[str, ...] = ()
    added_labels: tuple[str, ...] = ()
    removed_labels: tuple[str, ...] = ()
    blocking_messages: tuple[str, ...] = ()
    action_stage_hints: tuple[tuple[str, str, int], ...] = ()
    unsatisfied_prerequisites: tuple[tuple[str, str, str, int], ...] = ()
    last_action: str | None = None
    last_execution_accepted: bool | None = None
    last_execution_changed: bool | None = None
    last_consequence: tuple[str, ...] = ()
    rejected_actions: tuple[tuple[str, str | None, str], ...] = ()


class EvidenceTracker:
    """Maintain a bounded, observation-derived evidence record."""
    def __init__(self, *, max_rejections: int = 8) -> None:
        if max_rejections < 1:
            raise ValueError("max_rejections must be at least 1")
        self._previous = None
        self._current = None
        self._added_labels = ()
        self._removed_labels = ()
        self._rejections = []
        self._max_rejections = max_rejections

    def observe(self, observation: Observation) -> None:
        previous = self._current
        self._previous = previous
        self._current = observation
        if previous is None:
            self._added_labels = ()
            self._removed_labels = ()
            return
        before = _labels(previous)
        after = _labels(observation)
        self._added_labels = tuple(label for label in after if label not in before)
        self._removed_labels = tuple(label for label in before if label not in after)

    def record_rejection(self, decision, error: str) -> None:
        if decision is None:
            key, target = "unknown", None
        else:
            key, target = decision.action.type.value, decision.target_label or decision.action.target_id
        self._rejections.append((key, target, error))
        if len(self._rejections) > self._max_rejections:
            del self._rejections[0]

    def snapshot(self, history: tuple[ReasoningStep, ...] = ()) -> StateEvidence:
        if self._current is None:
            raise RuntimeError("cannot build evidence before an observation")
        labels = _labels(self._current)
        blocking = tuple(label for label in labels if _looks_blocking(label))
        hints = _stage_hints(self._current)
        last_action = accepted = changed = None
        consequence = ()
        if history:
            step = history[-1]
            last_action, accepted, changed = step.decision.action.type.value, step.execution.accepted, step.execution.changed
            if step.post_observation is not None:
                previous = _labels(self._previous) if self._previous is not None else ()
                current = _labels(step.post_observation)
                consequence = tuple(label for label in current if label not in previous)
        return StateEvidence(
            self._current.revision,
            self._previous.revision if self._previous else None,
            labels, self._added_labels, self._removed_labels, blocking, hints,
            _unsatisfied_prerequisites(self._current, blocking, hints),
            last_action, accepted, changed, consequence, tuple(self._rejections),
        )


def infer_unsatisfied_prerequisites(observation: Observation) -> tuple[tuple[str, str, str, int], ...]:
    """Return only high-confidence blockers explicitly supported by the UI."""
    labels = _labels(observation)
    blocking = tuple(label for label in labels if _looks_blocking(label))
    hints = _stage_hints(observation)
    return _unsatisfied_prerequisites(observation, blocking, hints)


def _labels(observation: Observation) -> tuple[str, ...]:
    return tuple(value for element in observation.elements if element.visible for value in (element.text, element.content_description) if value)


def _normalize(label: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", label.lower()))


def _looks_blocking(label: str) -> bool:
    return any(pattern.search(label) for pattern in _BLOCKING_PATTERNS)


def _stage_hints(observation: Observation) -> tuple[tuple[str, str, int], ...]:
    hints = []
    for element in observation.elements:
        if not element.visible or not element.enabled or not element.clickable:
            continue
        label = element.text or element.content_description
        if not label:
            continue
        stages = [_STAGE_WORDS[word] for word in re.findall(r"[a-z]+", label.lower()) if word in _STAGE_WORDS]
        if stages:
            hints.append((element.id, label, min(stages)))
    return tuple(hints)


def _unsatisfied_prerequisites(observation, blocking, hints):
    if not blocking or not hints:
        return ()
    normalized = [(i, l, s, _normalize(l)) for i, l, s in hints]
    result = []
    for message in blocking:
        match = next((pattern.search(message) for pattern in _BLOCKING_PATTERNS if pattern.search(message)), None)
        if not match:
            continue
        required = match.group("required").strip()
        required_norm = _normalize(required)
        prerequisite = next(((i, l, s) for i, l, s, norm in normalized if norm == required_norm or required_norm in norm or norm in required_norm), None)
        if prerequisite is None:
            continue
        required_id, required_label, required_stage = prerequisite
        for candidate_id, candidate_label, candidate_stage, _ in normalized:
            if candidate_id != required_id and candidate_stage > required_stage:
                result.append((candidate_id, candidate_label, required_label, required_stage))
    return tuple(dict.fromkeys(result))
