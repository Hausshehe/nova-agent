from __future__ import annotations

from typing import Any

from .reasoning_context import ReasoningContext


def reasoning_payload(context: ReasoningContext) -> dict[str, Any]:
    state = context.state
    statuses = [
        " ".join(part for part in (e.text, e.content_description) if part).strip()
        for e in state.elements
        if not e.clickable
    ]
    return {
        "goal": context.goal,
        "state": {
            "package": state.package,
            "activity": state.activity,
            "observation_id": state.observation_id,
            "status_text": [s for s in statuses if s],
        },
        "history": [dict(item) for item in context.history],
        "candidates": [
            {
                "action_type": c.action_type.value,
                "target": (
                    {
                        "element_id": c.target.element_id,
                        "text": c.target.text,
                        "content_description": c.target.content_description,
                    }
                    if c.target else None
                ),
                "enabled": c.enabled,
                "visible": c.visible,
            }
            for c in context.candidates
        ],
    }
