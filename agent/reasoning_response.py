from __future__ import annotations

from typing import Any, Mapping

from .core import Action, ActionType, Decision, Target
from .reasoning_context import ReasoningContext


class InvalidReasoningResponse(ValueError):
    """Raised when a provider response cannot be safely mapped to a Decision."""


def decision_from_response(
    response: Mapping[str, Any],
    context: ReasoningContext,
) -> Decision:
    """Validate a provider response against the current reasoning context."""
    if not isinstance(response, Mapping):
        raise InvalidReasoningResponse("response must be an object")

    action_type = response.get("action_type")
    try:
        action = ActionType(action_type)
    except (TypeError, ValueError) as exc:
        raise InvalidReasoningResponse("invalid action_type") from exc

    target_data = response.get("target")

    if action in (ActionType.BACK, ActionType.WAIT):
        if target_data is not None:
            raise InvalidReasoningResponse("target is not allowed for this action")
        return Decision(Action(action), str(response.get("reason", "provider decision")))

    if action is ActionType.CLICK:
        if not isinstance(target_data, Mapping):
            raise InvalidReasoningResponse("click action requires a target object")
        element_id = target_data.get("element_id")
        if not isinstance(element_id, str) or not element_id:
            raise InvalidReasoningResponse("click target requires element_id")
        candidate = next(
            (
                item for item in context.candidates
                if item.action_type is ActionType.CLICK
                and item.target is not None
                and item.target.element_id == element_id
            ),
            None,
        )
        if candidate is None:
            raise InvalidReasoningResponse("click target is not available in the current observation")
        if not candidate.enabled or not candidate.visible:
            raise InvalidReasoningResponse("click target is not enabled and visible")
        target = Target(element_id, candidate.target.text, candidate.target.content_description)
        return Decision(Action(ActionType.CLICK, target), str(response.get("reason", "provider decision")))

    if action is ActionType.SCROLL:
        if not isinstance(target_data, Mapping):
            raise InvalidReasoningResponse("scroll action requires a target object")
        element_id = target_data.get("element_id")
        if not isinstance(element_id, str) or not element_id:
            raise InvalidReasoningResponse("scroll target requires element_id")
        candidate = next(
            (
                item for item in context.candidates
                if item.action_type is ActionType.SCROLL
                and item.target is not None
                and item.target.element_id == element_id
            ),
            None,
        )
        if candidate is None:
            raise InvalidReasoningResponse("scroll target is not available in the current observation")
        if not candidate.enabled or not candidate.visible or not candidate.scrollable:
            raise InvalidReasoningResponse("scroll target is not enabled, visible, and scrollable")
        target = Target(element_id, candidate.target.text, candidate.target.content_description)
        return Decision(Action(ActionType.SCROLL, target), str(response.get("reason", "provider decision")))

    raise InvalidReasoningResponse("unsupported action type")
