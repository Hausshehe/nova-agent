"""Adapters that keep legacy and model-backed reasoning behind the v2 port."""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping, Protocol

from .models import Action, ActionType, Decision, Observation
from .ports import Reasoner
from .reasoning import ReasoningContext


class LegacyReasoner(Protocol):
    """Minimal legacy capability retained for compatibility during migration."""

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


class LLMReasoner:
    """Use an injected model responder through the v2 Reasoner protocol.

    The responder receives one JSON prompt containing only the current v2
    reasoning context and must return a mapping describing one action. No
    provider SDK, network policy, retry loop, or orchestration belongs here.
    """

    def __init__(self, responder: Callable[[str], Mapping[str, Any]]) -> None:
        self._responder = responder

    def decide(self, context: ReasoningContext) -> Decision:
        prompt = json.dumps(_reasoning_payload(context), ensure_ascii=False, separators=(",", ":"))
        try:
            response = self._responder(prompt)
        except Exception as exc:
            raise RuntimeError("reasoning provider failed") from exc
        if not isinstance(response, Mapping):
            raise ValueError("LLM response must be an object")
        return _decision_from_response(response, context)


def _observation_payload(observation: Observation) -> dict[str, Any]:
    return {
        "package": observation.package,
        "activity": observation.activity,
        "revision": observation.revision,
        "elements": [
            {
                "id": element.id,
                "text": element.text,
                "content_description": element.content_description,
                "clickable": element.clickable,
                "enabled": element.enabled,
                "class_name": element.class_name,
                "editable": element.editable,
                "scrollable": element.scrollable,
                "checkable": element.checkable,
                "checked": element.checked,
                "focused": element.focused,
                "visible": element.visible,
            }
            for element in observation.elements
        ],
    }


def _reasoning_payload(context: ReasoningContext) -> dict[str, Any]:
    """Serialize v2 context into a stable provider-neutral model payload."""

    return {
        "goal": context.goal.text,
        "reasoning_guidance": [
            "Determine the current UI state before choosing an action.",
            "Respect prerequisites and perform earlier required steps before later steps.",
            "Use visible status text and prior post-action observations as state evidence.",
            "After an action changes the UI, reassess the new state instead of repeating or skipping ahead.",
            "Prefer the smallest safe action that advances the goal from the current state.",
            "Do not assume an action succeeded semantically just because execution was accepted or changed the UI.",
        ],
        "observation": _observation_payload(context.observation),
        "history": [
            {
                "action_type": step.decision.action.type.value,
                "target_id": step.decision.action.target_id,
                "value": step.decision.action.value,
                "reason": step.decision.reason,
                "target_label": step.decision.target_label,
                "accepted": step.execution.accepted,
                "changed": step.execution.changed,
                "error": step.execution.error,
                "post_observation": (
                    _observation_payload(step.post_observation)
                    if step.post_observation is not None
                    else None
                ),
            }
            for step in context.history
        ],
    }


def _decision_from_response(
    response: Mapping[str, Any], context: ReasoningContext
) -> Decision:
    """Validate one model decision against the live v2 observation."""

    action_type = response.get("action_type")
    try:
        action = ActionType(action_type)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid action_type") from exc

    target_id = response.get("target_id")
    value = response.get("value")
    reason = str(response.get("reason", "model decision"))

    if target_id is not None and (not isinstance(target_id, str) or not target_id):
        raise ValueError("target_id must be a non-empty string or null")
    if value is not None and not isinstance(value, str):
        raise ValueError("value must be a string or null")

    if action in (ActionType.BACK, ActionType.WAIT):
        if target_id is not None or value is not None:
            raise ValueError("target_id and value are not allowed for this action")
        return Decision(Action(action), reason)

    if action is ActionType.TAP:
        if target_id is None or value is not None:
            raise ValueError("tap requires target_id and no value")
        element = next(
            (
                item
                for item in context.observation.elements
                if item.id == target_id
            ),
            None,
        )
        if element is None or not element.visible or not element.enabled or not element.clickable:
            raise ValueError("tap target is not available in the current observation")
        label = element.text or element.content_description
        return Decision(Action(action, target_id=target_id), reason, target_label=label)

    if action is ActionType.SCROLL:
        if target_id is not None:
            element = next(
                (item for item in context.observation.elements if item.id == target_id),
                None,
            )
            if element is None or not element.visible or not element.enabled or not element.scrollable:
                raise ValueError("scroll target is not available in the current observation")
        return Decision(Action(action, target_id=target_id), reason)

    if action is ActionType.TYPE:
        if target_id is None or value is None:
            raise ValueError("type requires target_id and value")
        element = next(
            (item for item in context.observation.elements if item.id == target_id),
            None,
        )
        if element is None or not element.visible or not element.enabled or not element.editable:
            raise ValueError("type target is not available in the current observation")
        return Decision(Action(action, target_id=target_id, value=value), reason)

    if action is ActionType.SWIPE:
        if target_id is None or value is None:
            raise ValueError("swipe requires target_id and value")
        return Decision(Action(action, target_id=target_id, value=value), reason)

    raise ValueError("unsupported action type")
