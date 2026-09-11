"""Deterministic uncertainty assessment and evidence-seeking guidance."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .models import Action, ActionType, Goal, Observation


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


@dataclass(frozen=True)
class EvidenceActionCandidate:
    """An observable action that may reduce a named uncertainty."""

    action: Action
    target_label: str
    resolves: str
    rationale: str
    score: int

    def snapshot(self) -> dict[str, object]:
        return {
            "action": self.action.type.value,
            "target_id": self.action.target_id,
            "target_label": self.target_label,
            "resolves": self.resolves,
            "rationale": self.rationale,
            "score": self.score,
        }


@dataclass(frozen=True)
class UncertaintyResolution:
    """Evidence-seeking options derived from the current observation."""

    candidates: tuple[EvidenceActionCandidate, ...] = ()
    guidance: tuple[str, ...] = ()

    def snapshot(self) -> dict[str, object]:
        return {
            "candidates": [candidate.snapshot() for candidate in self.candidates],
            "guidance": list(self.guidance),
        }


class UncertaintyResolutionPolicy:
    """Find observable actions that can answer explicit mission unknowns.

    This is deliberately a candidate generator, not an action selector. The
    current observation remains authoritative and the reasoner still chooses
    the final action.
    """

    _MAX_CANDIDATES = 4
    _STOPWORDS = {
        "the", "a", "an", "whether", "what", "which", "is", "are", "to",
        "the", "goal", "completion", "action", "another", "required", "current",
        "ui", "state", "best", "next", "effect", "intended", "may", "now",
    }

    def resolve(
        self,
        assessment: UncertaintyAssessment,
        observation: Observation,
        goal: Goal,
        *,
        excluded_target_ids: tuple[str, ...] = (),
    ) -> UncertaintyResolution:
        if assessment.level == "low":
            return UncertaintyResolution(
                guidance=("No information-gathering action is required because uncertainty is low.",),
            )

        excluded = set(excluded_target_ids)
        goal_tokens = self._tokens(goal.text)
        candidates: list[EvidenceActionCandidate] = []
        for unknown in assessment.unknowns:
            unknown_tokens = self._tokens(unknown)
            for element in observation.elements:
                if not element.visible or not element.enabled or element.id in excluded:
                    continue
                label = element.text or element.content_description
                if not label:
                    continue
                action = self._action_for(element)
                if action is None:
                    continue
                label_tokens = self._tokens(label)
                score = len(label_tokens & goal_tokens) * 3 + len(label_tokens & unknown_tokens) * 2
                if action.type is ActionType.SCROLL:
                    score += 1
                if "goal completion" in unknown:
                    score += len(label_tokens & goal_tokens)
                if score <= 0:
                    score = 1
                rationale = (
                    "Current UI evidence makes this action observable and it can provide new evidence "
                    "about the named unknown."
                )
                candidates.append(EvidenceActionCandidate(action, label, unknown, rationale, score))

        candidates.sort(key=lambda item: (-item.score, item.action.target_id or "", item.action.type.value))
        deduped: list[EvidenceActionCandidate] = []
        seen: set[tuple[str, str | None]] = set()
        for candidate in candidates:
            key = (candidate.action.type.value, candidate.action.target_id)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(candidate)
            if len(deduped) >= self._MAX_CANDIDATES:
                break

        if deduped:
            guidance = (
                "Uncertainty is operational: use a current-UI action that can produce fresh observable evidence.",
                "The candidate list is guidance, not permission; validate the target and expected evidence before acting.",
            )
        else:
            guidance = (
                "No current UI action clearly resolves the named unknown.",
                "Gather fresh observation or change context before inventing an information-gathering action.",
            )
        return UncertaintyResolution(tuple(deduped), guidance)

    @staticmethod
    def _action_for(element: object) -> Action | None:
        if getattr(element, "clickable", False):
            return Action(ActionType.TAP, target_id=element.id)
        if getattr(element, "editable", False):
            return Action(ActionType.TYPE, target_id=element.id)
        if getattr(element, "scrollable", False):
            return Action(ActionType.SCROLL, target_id=element.id)
        return None

    @classmethod
    def _tokens(cls, text: str) -> set[str]:
        return {
            token for token in re.findall(r"[a-z0-9]+", text.lower())
            if token not in cls._STOPWORDS
        }
