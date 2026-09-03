from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

from .core import Action, ActionType, ExecutionResult, WorldState, element_text
from .goal_evaluator import GoalEvaluator


class TaskEffect(str, Enum):
    """Semantic consequence of an executed action for the current task."""

    PROGRESSED = "progressed"
    BLOCKED = "blocked"
    FAILED = "failed"
    COMPLETED = "completed"
    UNKNOWN = "unknown"


_FAILURE_PHRASES = (
    "failed",
    "failure",
    "error",
    "unable",
    "cannot",
    "can't",
    "denied",
    "invalid",
    "not allowed",
    "not permitted",
    "try again",
    "previous steps",
)

_COMPLETION_PHRASES = (
    "completed",
    "complete",
    "finished",
    "finish success",
    "success",
    "successful",
    "done",
)


@dataclass(frozen=True)
class TaskEffectResult:
    effect: TaskEffect
    evidence: str = ""


class TaskEffectEvaluator:
    """Translate execution + fresh UI evidence into a task-level effect."""

    def __init__(self, goal_evaluator: GoalEvaluator | None = None) -> None:
        self.goal_evaluator = goal_evaluator or GoalEvaluator()

    def evaluate(
        self,
        goal: str,
        action: Action,
        result: ExecutionResult,
        before: WorldState,
        after: WorldState | None,
    ) -> TaskEffectResult:
        if not result.accepted:
            return TaskEffectResult(TaskEffect.FAILED, result.error or "action rejected")

        if after is None:
            return TaskEffectResult(TaskEffect.UNKNOWN, result.error or "no post-action observation")

        evidence = self._failure_evidence(after)
        if evidence:
            return TaskEffectResult(TaskEffect.BLOCKED, evidence)

        # Global actions such as BACK and WAIT retain their established
        # semantic completion rules. Click/open goals are stricter: execution
        # success alone is never proof that the requested task outcome was
        # achieved.
        if action.type is not ActionType.CLICK and self.goal_evaluator.action_goal_satisfied(
            goal, action, after
        ):
            return TaskEffectResult(TaskEffect.COMPLETED)

        if action.type is ActionType.CLICK and self._completion_evidence(
            goal, action, before, after
        ):
            return TaskEffectResult(TaskEffect.COMPLETED)

        if not result.changed or before == after:
            return TaskEffectResult(TaskEffect.UNKNOWN, "accepted action produced no verified state change")

        return TaskEffectResult(TaskEffect.PROGRESSED)

    @staticmethod
    def _completion_evidence(
        goal: str,
        action: Action,
        before: WorldState,
        after: WorldState,
    ) -> bool:
        """Require concrete post-action evidence before declaring a click complete."""
        tokens = re.findall(r"[a-z0-9]+", goal.lower())
        if not tokens or tokens[0] not in {"tap", "click", "open"}:
            return False
        target = action.target
        if target is None:
            return False

        # The strongest generic completion signal is that the actionable
        # target which was selected is no longer present after the transition.
        # Match by stable id first, with text/content-description fallback for
        # providers that do not preserve resource ids.
        before_target = next(
            (element for element in before.elements if TaskEffectEvaluator._target_matches(element, target)),
            None,
        )
        if before_target is not None and not any(
            TaskEffectEvaluator._target_matches(element, target) for element in after.elements
        ):
            return True

        for element in after.elements:
            if element.clickable:
                continue
            text = element_text(element).strip()
            normalized = " ".join(re.findall(r"[a-z0-9]+", text.lower()))
            if any(phrase in normalized for phrase in _COMPLETION_PHRASES):
                return True
        return False

    @staticmethod
    def _target_matches(element, target) -> bool:
        if target.element_id and element.id == target.element_id:
            return True
        target_text = target.text.strip().lower()
        target_description = target.content_description.strip().lower()
        element_text_value = element.text.strip().lower()
        element_description = element.content_description.strip().lower()
        return bool(
            (target_text and element_text_value == target_text)
            or (target_description and element_description == target_description)
        )

    @staticmethod
    def _failure_evidence(state: WorldState) -> str:
        for element in state.elements:
            if element.clickable:
                continue
            text = element_text(element).strip()
            normalized = " ".join(re.findall(r"[a-z0-9]+", text.lower()))
            if any(phrase in normalized for phrase in _FAILURE_PHRASES):
                return text
        return ""
