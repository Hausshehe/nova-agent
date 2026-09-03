from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .core import Action, ActionType, WorldState
from .task_effect import TaskEffect, TaskEffectResult


@dataclass(frozen=True)
class ActionConstraint:
    """Evidence-backed restriction on repeating one action in the current state."""

    action_type: ActionType
    target_id: str | None
    reason: str
    evidence: str
    observation_id: str
    state_fingerprint: str

    def matches(self, action: Action) -> bool:
        return (
            self.action_type is action.type
            and self.target_id == (action.target.element_id if action.target else None)
        )

    def is_active(self, state: WorldState) -> bool:
        return self.state_fingerprint == state_fingerprint(state)


def state_fingerprint(state: WorldState) -> str:
    """Stable representation used to scope constraints to observed UI state."""
    parts = [state.package, state.activity]
    for element in state.elements:
        parts.append(
            "|".join(
                (
                    element.id,
                    element.text,
                    element.content_description,
                    str(element.clickable),
                    str(element.enabled),
                    str(element.visible),
                    str(element.checked),
                    str(element.scrollable),
                )
            )
        )
    return "\n".join(parts)


@dataclass
class TaskState:
    """Small working memory for task consequences and temporary constraints."""

    effect: TaskEffect = TaskEffect.UNKNOWN
    effect_evidence: str = ""
    constraints: list[ActionConstraint] = field(default_factory=list)

    def reset(self) -> None:
        self.effect = TaskEffect.UNKNOWN
        self.effect_evidence = ""
        self.constraints.clear()

    def apply(
        self,
        action: Action,
        effect: TaskEffectResult,
        state_before: WorldState,
        state_after: WorldState | None,
    ) -> None:
        self.effect = effect.effect
        self.effect_evidence = effect.evidence

        # Constraints are scoped to the exact observed UI state. They are not
        # permanent prohibitions and cannot encode an app-specific workflow.
        if effect.effect is TaskEffect.BLOCKED and state_after is not None:
            constraint = ActionConstraint(
                action_type=action.type,
                target_id=action.target.element_id if action.target else None,
                reason="action blocked by observed task evidence",
                evidence=effect.evidence,
                observation_id=state_after.observation_id,
                state_fingerprint=state_fingerprint(state_after),
            )
            self.constraints = [
                existing for existing in self.constraints if not existing.matches(action)
            ]
            self.constraints.append(constraint)
            return

        if state_after is None:
            return

        self.constraints = [
            constraint
            for constraint in self.constraints
            if constraint.is_active(state_after)
        ]

    def active_constraints(self, state: WorldState) -> tuple[ActionConstraint, ...]:
        return tuple(constraint for constraint in self.constraints if constraint.is_active(state))

    def is_constrained(self, action: Action, state: WorldState) -> bool:
        return any(constraint.matches(action) for constraint in self.active_constraints(state))

    def constrained_action_keys(self, state: WorldState) -> frozenset[tuple[str, str | None]]:
        return frozenset(
            (constraint.action_type.value, constraint.target_id)
            for constraint in self.active_constraints(state)
        )

    def as_context(self, state: WorldState) -> dict[str, Any]:
        return {
            "last_effect": self.effect.value,
            "last_effect_evidence": self.effect_evidence,
            "active_constraints": [
                {
                    "action_type": constraint.action_type.value,
                    "target_id": constraint.target_id,
                    "reason": constraint.reason,
                    "evidence": constraint.evidence,
                }
                for constraint in self.active_constraints(state)
            ],
        }
