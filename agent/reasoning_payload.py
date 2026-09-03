from __future__ import annotations

from typing import Any

from .reasoning_context import ReasoningContext


def reasoning_payload(context: ReasoningContext) -> dict[str, Any]:
    """Convert reasoning context into a compact, model/provider-neutral payload."""
    state = context.state
    return {
        "goal": context.goal,
        "state": {
            "package": state.package,
            "activity": state.activity,
            "observation_id": state.observation_id,
            "elements": [
                {
                    "id": element.id,
                    "text": element.text,
                    "content_description": element.content_description,
                    "clickable": element.clickable,
                    "enabled": element.enabled,
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
            }
            for candidate in context.candidates
        ],
    }
