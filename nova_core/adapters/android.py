"""Android adapters that translate the legacy bridge into v2 ports.

The v2 core knows nothing about Android or the legacy ``agent`` package. This
module is the compatibility seam: Android-specific behavior stays here while
v2 receives only its own models and port contracts.
"""

from __future__ import annotations

import re

from agent.android_bridge import AndroidBridge
from agent.core import Action as LegacyAction
from agent.core import ActionType as LegacyActionType
from agent.core import Target as LegacyTarget

from ..models import Action, ActionType, ExecutionResult, Goal, Observation, UiElement


class AndroidBridgeAdapter:
    """Expose the existing localhost Android bridge through v2 ports."""

    def __init__(self, bridge: AndroidBridge | None = None) -> None:
        self.bridge = bridge or AndroidBridge()
        self._revision = 0

    def observe(self) -> Observation:
        state = self.bridge.observe()
        self._revision += 1
        return Observation(
            package=state.package,
            activity=state.activity,
            elements=tuple(
                UiElement(
                    id=element.id,
                    text=element.text,
                    content_description=element.content_description,
                    clickable=element.clickable,
                    enabled=element.enabled,
                    visible=element.visible,
                )
                for element in state.elements
            ),
            revision=self._revision,
        )

    def execute(self, action: Action) -> ExecutionResult:
        legacy_action = self._to_legacy_action(action)
        if legacy_action is None:
            return ExecutionResult(
                accepted=False,
                changed=False,
                error=f"unsupported v2 action type: {action.type.value}",
            )
        result = self.bridge.execute(legacy_action)
        return ExecutionResult(
            accepted=result.accepted,
            changed=result.changed,
            error=result.error,
        )

    @staticmethod
    def _to_legacy_action(action: Action) -> LegacyAction | None:
        if action.type is ActionType.TAP:
            if action.target_id is None:
                return None
            return LegacyAction(
                type=LegacyActionType.CLICK,
                target=LegacyTarget(element_id=action.target_id),
            )
        if action.type is ActionType.BACK:
            return LegacyAction(type=LegacyActionType.BACK)
        if action.type is ActionType.SCROLL:
            if action.target_id is None:
                return None
            return LegacyAction(
                type=LegacyActionType.SCROLL,
                target=LegacyTarget(element_id=action.target_id),
            )
        return None


class AndroidGoalVerifier:
    """Conservative UI verifier with an injectable completion evaluator.

    The evaluator is deliberately supplied by the caller. This keeps goal
    semantics separate from Android transport and prevents the adapter from
    inventing completion rules that may later be replaced by a stronger
    reasoning/evaluation layer.
    """

    def __init__(self, goal_evaluator) -> None:
        self.goal_evaluator = goal_evaluator

    def verify(
        self,
        goal: Goal,
        before: Observation,
        decision,
        result: ExecutionResult,
        after: Observation,
    ) -> bool:
        if not result.accepted or not result.changed:
            return False
        if before == after:
            return False
        return bool(self.goal_evaluator(goal.text, after))
