from __future__ import annotations

from typing import Any

from .reasoning_context import ReasoningContext


def reasoning_payload(context: ReasoningContext) -> dict[str, Any]:
    """Convert reasoning context into a compact, model/provider-neutral payload."""
    state = context.state
    status_text = [
        " ".join(part for part in (element.text, element.content_description) if part).strip()
        for element in state.elements
        if not element.clickable
    ]
    status_text = [text for text in status_text if text]

    current_ui = [
        {
            "element_id": element.id,
            "text": element.text,
            "content_description": element.content_description,
            "clickable": element.clickable,
            "enabled": element.enabled,
            "visible": element.visible,
            "scrollable": element.scrollable,
        }
        for element in state.elements
    ]

    payload = {
        "goal": context.goal,
        "state": {
            "package": state.package,
            "activity": state.activity,
            "observation_id": state.observation_id,
            "status_text": status_text,
            "current_ui": current_ui,
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
            }
            for candidate in context.candidates
        ],
    }
    if context.task_state is not None:
        payload["task_state"] = context.task_state.as_context(state)
    return payload
