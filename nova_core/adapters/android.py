"""Android adapters that translate the legacy bridge into v2 ports.

The v2 core knows nothing about Android or the legacy ``agent`` package. This
module is the compatibility seam: Android-specific behavior stays here while
v2 receives only its own models and port contracts.
"""

from __future__ import annotations

import time
from typing import Callable

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
        self._last_legacy_state = None

    @staticmethod
    def _to_observation(state, revision: int) -> Observation:
        elements = []
        for element in state.elements:
            elements.append(
                UiElement(
                    id=element.id,
                    text=getattr(element, "text", ""),
                    content_description=getattr(element, "content_description", ""),
                    clickable=getattr(element, "clickable", False),
                    enabled=getattr(element, "enabled", True),
                    class_name=getattr(element, "class_name", ""),
                    editable=getattr(element, "editable", False),
                    scrollable=getattr(element, "scrollable", False),
                    checkable=getattr(element, "checkable", False),
                    checked=getattr(element, "checked", False),
                    focused=getattr(element, "focused", False),
                    visible=getattr(element, "visible", True),
                )
            )
        return Observation(
            package=state.package,
            activity=state.activity,
            elements=tuple(elements),
            revision=revision,
        )

    def observe(self) -> Observation:
        state = self._observe_initial_ready() if self._revision == 0 else self.bridge.observe()
        self._last_legacy_state = state
        self._revision += 1
        return self._to_observation(state, self._revision)

    def _observe_initial_ready(self):
        """Wait briefly for the launched Activity to expose a usable UI tree."""
        state = self.bridge.observe()
        if state.elements:
            return state
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            time.sleep(0.2)
            state = self.bridge.observe()
            if state.elements:
                return state
        return state

    def observe_fresh(self, previous: Observation) -> Observation:
        if self._last_legacy_state is None:
            raise ValueError("cannot observe fresh state before an initial observation")
        state = self.bridge.wait_for_fresh_observation(
            self._last_legacy_state, timeout=2.0, poll_seconds=0.2
        )
        self._last_legacy_state = state
        self._revision += 1
        return self._to_observation(state, self._revision)

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
    """Conservative UI verifier with an injectable completion evaluator."""

    def __init__(self, goal_evaluator: Callable[[str, Observation], bool]) -> None:
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
