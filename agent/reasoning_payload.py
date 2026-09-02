from __future__ import annotations

from typing import Any

from .reasoning_context import ReasoningContext


def reasoning_payload(context: ReasoningContext) -> dict[str, Any]:
    """Convert reasoning context into a stable, model/provider-neutral payload."""
    state = context.state
    return {
        "goal": context.goal,
        "state": {
            "package": state.package,
            "activity": state.activity,
            "observation_id": state.observation_id,
            "timestamp_ms": state.timestamp_ms,
            "elements": [
                {
                    "id": element.id,
                    "text": element.text,
                    "content_description": element.content_description,
                    "clickable": element.clickable,
                    "enabled": element.enabled,
                    "class_name": element.class_name,
                    "bounds": element.bounds,
                    "editable": element.editable,
                    "scrollable": element.scrollable,
                    "checkable": element.checkable,
                    "checked": element.checked,
                    "focused": element.focused,
                    "visible": element.visible,
                }
                for element in state.elements
            ],
        },
        "history": [dict(item) for item in context.history],
        "candidates": [
            {
                "action_type": candidate.action_type.value,
                "target": (
                    {
                        "element_id": candidate.target.element_id,
                        "text": candidate.target.text,
                        "content_description": candidate.target.content_description,
                    }
                    if candidate.target is not None
                    else None
                ),
                "enabled": candidate.enabled,
                "visible": candidate.visible,
                "class_name": candidate.class_name,
                "bounds": candidate.bounds,
                "editable": candidate.editable,
                "scrollable": candidate.scrollable,
                "checkable": candidate.checkable,
                "checked": candidate.checked,
                "focused": candidate.focused,
            }
            for candidate in context.candidates
        ],
    }
