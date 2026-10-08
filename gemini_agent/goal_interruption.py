"""Bounded interruption and resumption state transitions for Nova's 184 multi-goal agency phase."""

from __future__ import annotations

from dataclasses import dataclass

_MAX_TEXT = 512
_MAX_ACTIONS = 4


@dataclass(frozen=True)
class GoalInterruptionState:
    """Represent one goal's bounded pause/resume state without executing it."""

    goal_id: str
    status: str
    checkpoint: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.goal_id, "Goal id"),
            (self.checkpoint, "Checkpoint"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} cannot be empty.")
            if len(value.strip()) > _MAX_TEXT:
                raise ValueError(f"{label} is too long.")
        if self.status not in {"ACTIVE", "PAUSED"}:
            raise ValueError("Goal interruption status must be ACTIVE or PAUSED.")


def manage_goal_interruption(goal: str) -> str:
    """Apply bounded PAUSE/RESUME transitions to one supplied goal state.

    Format:
        goal_id | status | checkpoint | action[, action...]

    Only PAUSE from ACTIVE and RESUME from PAUSED are accepted. The checkpoint
    is preserved across every transition and no goal work or device action runs.
    """
    if not isinstance(goal, str) or not goal.strip():
        raise ValueError("Goal interruption request cannot be empty.")

    parts = [part.strip() for part in goal.strip().split("|")]
    if len(parts) != 4:
        raise ValueError(
            "Goal interruption must use: goal_id | status | checkpoint | action[, action...]"
        )

    goal_id, status, checkpoint, actions_text = parts
    actions = [item.strip().upper() for item in actions_text.split(",") if item.strip()]
    if not actions:
        raise ValueError("At least one interruption action is required.")
    if len(actions) > _MAX_ACTIONS:
        raise ValueError(f"No more than {_MAX_ACTIONS} interruption actions are allowed.")

    state = GoalInterruptionState(goal_id, status.upper(), checkpoint)
    initial_checkpoint = state.checkpoint
    lines = [
        "Goal interruption/resumption (bounded state transition):",
        f"Goal id: {state.goal_id.strip()}",
        f"Initial status: {state.status}",
        f"Checkpoint: {state.checkpoint.strip()}",
    ]

    for action in actions:
        if action == "PAUSE":
            if state.status != "ACTIVE":
                raise ValueError("PAUSE requires the goal to be ACTIVE.")
            state = GoalInterruptionState(state.goal_id, "PAUSED", state.checkpoint)
        elif action == "RESUME":
            if state.status != "PAUSED":
                raise ValueError("RESUME requires the goal to be PAUSED.")
            state = GoalInterruptionState(state.goal_id, "ACTIVE", state.checkpoint)
        else:
            raise ValueError("Interruption action must be PAUSE or RESUME.")
        lines.append(f"Transition: {action} -> {state.status}")

    lines.extend([
        f"Final status: {state.status}",
        f"Checkpoint preserved: {'YES' if state.checkpoint == initial_checkpoint else 'NO'}",
        "Boundary: interruption changes only the supplied goal-state representation; no goal work was executed or completed.",
        "No device state was changed.",
    ])
    return "\n".join(lines)
