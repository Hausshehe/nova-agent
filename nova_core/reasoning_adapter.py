"""Adapters that keep legacy and model-backed reasoning behind the v2 port."""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping, Protocol

from .models import Action, ActionType, Decision, Observation
from .ports import Reasoner
from .reasoning import ReasoningContext


class LegacyReasoner(Protocol):
    def decide(self, goal: str, observation: object, history: tuple) -> object:
        ...


class LegacyReasoningAdapter:
    def __init__(self, provider: LegacyReasoner) -> None:
        self._provider = provider

    def decide(self, context: ReasoningContext) -> Decision:
        raw = self._provider.decide(context.goal.text, context.observation, context.history)
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
    def __init__(self, responder: Callable[[str], Mapping[str, Any]]) -> None:
        self._responder = responder

    def decide(self, context: ReasoningContext) -> Decision:
        prompt = json.dumps(_reasoning_payload(context), ensure_ascii=False, separators=(",", ":"))
        try:
            response = self._responder(prompt)
        except Exception as exc:
            raise RuntimeError(f"reasoning provider failed: {exc}") from exc
        if not isinstance(response, Mapping):
            raise ValueError("LLM response must be an object")
        return _decision_from_response(response, context)


def _observation_payload(observation: Observation) -> dict[str, Any]:
    return {
        "package": observation.package,
        "activity": observation.activity,
        "revision": observation.revision,
        "elements": [
            {"id": e.id, "text": e.text, "content_description": e.content_description,
             "clickable": e.clickable, "enabled": e.enabled, "class_name": e.class_name,
             "editable": e.editable, "scrollable": e.scrollable, "checkable": e.checkable,
             "checked": e.checked, "focused": e.focused, "visible": e.visible}
            for e in observation.elements
        ],
    }


def _observation_history_summary(observation: Observation | None) -> dict[str, Any] | None:
    if observation is None:
        return None
    return {
        "package": observation.package,
        "activity": observation.activity,
        "revision": observation.revision,
        "elements": [{"text": e.text or None, "content_description": e.content_description or None}
                     for e in observation.elements if e.visible and (e.text or e.content_description)],
        "visible_text": [text for e in observation.elements if e.visible for text in (e.text, e.content_description) if text],
    }


def _reasoning_payload(context: ReasoningContext) -> dict[str, Any]:
    evidence = context.evidence
    evidence_payload = None
    if evidence is not None:
        evidence_payload = {
            "current_revision": evidence.current_revision,
            "previous_revision": evidence.previous_revision,
            "visible_labels": list(evidence.visible_labels),
            "added_labels": list(evidence.added_labels),
            "removed_labels": list(evidence.removed_labels),
            "blocking_messages": list(evidence.blocking_messages),
            "action_stage_hints": [{"id": i, "label": l, "stage": s} for i, l, s in evidence.action_stage_hints],
            "unsatisfied_prerequisites": [
                {"candidate_id": i, "candidate_label": l, "required_label": r, "required_stage": s}
                for i, l, r, s in evidence.unsatisfied_prerequisites
            ],
            "last_action": evidence.last_action,
            "last_execution_accepted": evidence.last_execution_accepted,
            "last_execution_changed": evidence.last_execution_changed,
            "last_consequence": list(evidence.last_consequence),
            "rejected_actions": [{"action_type": t, "target": target, "error": error} for t, target, error in evidence.rejected_actions],
        }
    return {
        "goal": context.goal.text,
        "reasoning_guidance": [
            "Determine the current UI state before choosing an action.",
            "Treat current observation as authoritative; history is evidence, not current state.",
            "An unsatisfied_prerequisite is a high-confidence blocker derived from explicit UI evidence. Do not choose its candidate action until the prerequisite is satisfied.",
            "Use blocking messages as evidence about what must happen before another action.",
            "Use action_stage_hints only as generic ordering evidence, never as a hard-coded workflow.",
            "After an action changes the UI, reassess the new state instead of repeating or skipping ahead.",
            "Prefer the smallest safe action that advances the goal from the current state.",
            "Never invent an element id or execute an action that the current observation does not support.",
        ],
        "observation": _observation_payload(context.observation),
        "evidence": evidence_payload,
        "history": [{
            "action_type": s.decision.action.type.value, "target_id": s.decision.action.target_id,
            "value": s.decision.action.value, "reason": s.decision.reason, "target_label": s.decision.target_label,
            "accepted": s.execution.accepted, "changed": s.execution.changed, "error": s.execution.error,
            "post_observation": _observation_history_summary(s.post_observation),
        } for s in context.history],
    }


def _decision_from_response(response: Mapping[str, Any], context: ReasoningContext) -> Decision:
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
        element = next((item for item in context.observation.elements if item.id == target_id), None)
        if element is None or not element.visible or not element.enabled or not element.clickable:
            raise ValueError("tap target is not available in the current observation")
        return Decision(Action(action, target_id=target_id), reason, target_label=element.text or element.content_description)
    if action is ActionType.SCROLL:
        if target_id is not None:
            element = next((item for item in context.observation.elements if item.id == target_id), None)
            if element is None or not element.visible or not element.enabled or not element.scrollable:
                raise ValueError("scroll target is not available in the current observation")
        return Decision(Action(action, target_id=target_id), reason)
    if action is ActionType.TYPE:
        if target_id is None or value is None:
            raise ValueError("type requires target_id and value")
        element = next((item for item in context.observation.elements if item.id == target_id), None)
        if element is None or not element.visible or not element.enabled or not element.editable:
            raise ValueError("type target is not available in the current observation")
        return Decision(Action(action, target_id=target_id, value=value), reason)
    if action is ActionType.SWIPE:
        if target_id is None or value is None:
            raise ValueError("swipe requires target_id and value")
        element = next((item for item in context.observation.elements if item.id == target_id), None)
        if element is None or not element.visible or not element.enabled:
            raise ValueError("swipe target is not available in the current observation")
        return Decision(Action(action, target_id=target_id, value=value), reason)
    raise ValueError("unsupported action type")
