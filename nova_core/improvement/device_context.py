"""Bounded Android evidence exposed to Nova's self-repair brain."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import Decision, ExecutionResult, Observation

MAX_ELEMENTS = 32
MAX_TEXT_CHARS = 240
MAX_VISIBLE_LINE_CHARS = 1_200


@dataclass(frozen=True)
class DeviceEvidence:
    """Small, auditable snapshot of the device state relevant to a failure."""

    package: str
    activity: str
    revision: int
    visible_elements: tuple[str, ...]
    last_action: str | None = None
    action_accepted: bool | None = None
    action_changed: bool | None = None
    action_error: str | None = None
    previous_revision: int | None = None

    @classmethod
    def from_runtime(
        cls,
        observation: Observation,
        decision: Decision | None = None,
        execution: ExecutionResult | None = None,
        previous: Observation | None = None,
    ) -> "DeviceEvidence":
        labels: list[str] = []
        for element in observation.elements[:MAX_ELEMENTS]:
            label = element.text.strip() or element.content_description.strip() or element.id
            labels.append(label[:MAX_TEXT_CHARS])
        action = None
        if decision is not None:
            action = decision.action.type.value
            if decision.action.target_id:
                action += f" target={decision.action.target_id}"
        return cls(
            package=observation.package,
            activity=observation.activity,
            revision=observation.revision,
            visible_elements=tuple(labels),
            last_action=action,
            action_accepted=None if execution is None else execution.accepted,
            action_changed=None if execution is None else execution.changed,
            action_error=None if execution is None else execution.error,
            previous_revision=None if previous is None else previous.revision,
        )

    def bounded_lines(self) -> tuple[str, ...]:
        visible = " | ".join(self.visible_elements)[:MAX_VISIBLE_LINE_CHARS]
        lines = [
            f"device.package={self.package}",
            f"device.activity={self.activity}",
            f"device.revision={self.revision}",
            f"device.previous_revision={self.previous_revision}",
            f"device.last_action={self.last_action}",
            f"device.action_accepted={self.action_accepted}",
            f"device.action_changed={self.action_changed}",
            f"device.action_error={(self.action_error or '')[:MAX_TEXT_CHARS]}",
            f"device.visible_elements={visible}",
        ]
        return tuple(lines)
