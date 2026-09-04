"""Adapter boundary for legacy reasoning providers.

The v2 runtime talks only to the v2 Reasoner protocol. This module defines a
small translation seam for a legacy provider without importing or embedding
legacy navigation orchestration.
"""

from __future__ import annotations

from typing import Protocol, Any

from .models import Action, ActionType, Decision
from .ports import Reasoner
from .reasoning import ReasoningContext


class LegacyReasoner(Protocol):
    """Minimal provider capability required by the adapter."""

    def decide(self, goal: str, observation: object, history: tuple) -> object:
        ...


class LegacyReasoningAdapter:
    """Translate a small legacy decision shape into a v2 Decision.

    Malformed or unsupported provider output fails closed.
    """

    def __init__(self, provider: LegacyReasoner) -> None:
        self._provider = provider

    def decide(self, context: ReasoningContext) -> Decision:
        raw = self._provider.decide(
            context.goal.text,
            context.observation,
            context.history,
        )
        return self._translate(raw)

    @staticmethod
    def _translate(raw: object) -> Decision:
        if not isinstance(raw, dict):
            raise ValueError("legacy reasoner must return a mapping")

        action_type = raw.get("action_type")
        target = raw.get("target")
        target_id = target.get("element_id") if isinstance(target, dict) else None
        reason = str(raw.get("reason", "legacy provider decision"))

        if action_type == "click":
            if not isinstance(target_id, str) or not target_id:
                raise ValueError("legacy click decision requires target.element_id")
            return Decision(Action(ActionType.TAP, target_id=target_id), reason)

        if action_type == "back":
            return Decision(Action(ActionType.BACK), reason)

        if action_type == "scroll":
            return Decision(Action(ActionType.SCROLL, target_id=target_id), reason)

        raise ValueError(f"unsupported legacy action type: {action_type!r}")
