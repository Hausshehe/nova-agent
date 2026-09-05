"""Independent pre-execution action guard for Nova Agent v2."""

from __future__ import annotations

from dataclasses import dataclass

from .evidence import StateEvidence
from .models import ActionType, Decision, Observation


@dataclass(frozen=True)
class GuardResult:
    allowed: bool
    reason: str = ""


class ActionGuard:
    """Validate an already-selected action against live observation/evidence."""

    def check(
        self,
        decision: Decision,
        observation: Observation,
        evidence: StateEvidence | None = None,
    ) -> GuardResult:
        action = decision.action
        if action.type in (ActionType.BACK, ActionType.WAIT):
            if action.target_id is not None or action.value is not None:
                return GuardResult(False, "action cannot carry target or value")
            return GuardResult(True)

        if action.type is ActionType.TAP:
            element = self._target(action.target_id, observation)
            if element is None:
                return GuardResult(False, "tap target is not present")
            if not element.visible:
                return GuardResult(False, "tap target is not visible")
            if not element.enabled:
                return GuardResult(False, "tap target is disabled")
            if not element.clickable:
                return GuardResult(False, "tap target is not clickable")
            if action.value is not None:
                return GuardResult(False, "tap cannot carry a value")
            if evidence is not None:
                blocked = next(
                    (
                        (candidate, prerequisite)
                        for candidate, _label, prerequisite, _stage in evidence.unsatisfied_prerequisites
                        if candidate == action.target_id
                    ),
                    None,
                )
                if blocked is not None:
                    return GuardResult(
                        False,
                        f"tap target has unsatisfied prerequisite: {blocked[1]}",
                    )
            return GuardResult(True)

        if action.type is ActionType.TYPE:
            element = self._target(action.target_id, observation)
            if element is None:
                return GuardResult(False, "type target is not present")
            if not element.visible or not element.enabled or not element.editable:
                return GuardResult(False, "type target is not editable and available")
            if action.value is None:
                return GuardResult(False, "type requires a value")
            return GuardResult(True)

        if action.type is ActionType.SCROLL:
            if action.value is not None:
                return GuardResult(False, "scroll cannot carry a value")
            if action.target_id is None:
                return GuardResult(True)
            element = self._target(action.target_id, observation)
            if element is None or not element.visible or not element.enabled or not element.scrollable:
                return GuardResult(False, "scroll target is not scrollable and available")
            return GuardResult(True)

        if action.type is ActionType.SWIPE:
            if action.target_id is None or action.value is None:
                return GuardResult(False, "swipe requires target and value")
            element = self._target(action.target_id, observation)
            if element is None or not element.visible or not element.enabled:
                return GuardResult(False, "swipe target is not available")
            return GuardResult(True)

        return GuardResult(False, "unsupported action type")

    @staticmethod
    def _target(target_id: str | None, observation: Observation):
        if target_id is None:
            return None
        return next((element for element in observation.elements if element.id == target_id), None)
