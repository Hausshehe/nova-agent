from __future__ import annotations

from typing import Any, Mapping

from .core import Action, ActionType, Decision, Target
from .reasoning_context import ReasoningContext


class InvalidReasoningResponse(ValueError):
    pass


def decision_from_response(response: Mapping[str, Any], context: ReasoningContext) -> Decision:
    action_type = response.get("action_type")
    try:
        action = ActionType(action_type)
    except (TypeError, ValueError) as exc:
        raise InvalidReasoningResponse("invalid action_type") from exc

    candidate_types = {candidate.action_type for candidate in context.candidates}
    if action not in candidate_types:
        raise InvalidReasoningResponse(f"action type is not currently available: {action.value}")

    target_data = response.get("target")
    if action is ActionType.BACK:
        if target_data is not None:
            raise InvalidReasoningResponse("target is not allowed for this action")
        return Decision(Action(action), str(response.get("reason", "provider decision")))

    if action is ActionType.WAIT:
        raise InvalidReasoningResponse("unsupported action type")

    if action is not ActionType.CLICK:
        raise InvalidReasoningResponse("unsupported action type")
    if not isinstance(target_data, Mapping):
        raise InvalidReasoningResponse("click action requires a target object")
    element_id = target_data.get("element_id")
    if not isinstance(element_id, str) or not element_id:
        raise InvalidReasoningResponse("click target requires element_id")

    candidate = next((c for c in context.candidates if c.action_type is ActionType.CLICK and c.target and c.target.element_id == element_id), None)
    if candidate is None or not candidate.enabled or not candidate.visible:
        raise InvalidReasoningResponse("click target is not currently actionable")
    target = Target(element_id, candidate.target.text, candidate.target.content_description)
    return Decision(Action(ActionType.CLICK, target), str(response.get("reason", "provider decision")))
