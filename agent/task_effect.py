from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

from .core import Action, ExecutionResult, WorldState, element_text
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

        # Click/open/tap goals require actual post-action evidence. A matching
        # button being clicked is execution success, not proof that the task
        # outcome was achieved.
        if action.type is not action.type.CLICK and self.goal_evaluator.action_goal_satisfied(
            goal, action, after
        ):
            return TaskEffectResult(TaskEffect.COMPLETED)

        if action.type is action.type.CLICK and self._completion_evidence(
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
        """Require post-action evidence before declaring a click goal complete."""
        tokens = re.findall(r"[a-z0-9]+", goal.lower())
        if not tokens or tokens[0] not in {"tap", "click", "open"}:
            return False
        if action.target is None:
            return False

        target_id = action.target.element_id
        if target_id and not any(element.id == target_id for element in after.elements):
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
    def _failure_evidence(state: WorldState) -> str:
        for element in state.elements:
            if element.clickable:
                continue
            text = element_text(element).strip()
            normalized = " ".join(re.findall(r"[a-z0-9]+", text.lower()))
            if any(phrase in normalized for phrase in _FAILURE_PHRASES):
                return text
        return ""
