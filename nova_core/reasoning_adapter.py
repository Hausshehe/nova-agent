from __future__ import annotations

import json
import re
from typing import Any, Callable, Mapping

from .models import Action, ActionType, Decision, Observation
from .reasoning import ReasoningContext


_MAX_VISIBLE_ELEMENTS = 24
_MAX_HISTORY_STEPS = 6
_MAX_REASON_LENGTH = 500


def _normalize(value: str) -> str:
    return " ".join(value.lower().split())


def _label(element: Any) -> str:
    return element.text or element.content_description or element.id


def _observation_payload(observation: Observation) -> dict[str, Any]:
    elements = []
    for element in observation.elements:
        if not element.visible or not element.enabled:
            continue
        if not (element.clickable or element.editable or element.scrollable):
            continue
        elements.append({
            "id": element.id,
            "label": _label(element),
            "clickable": element.clickable,
            "editable": element.editable,
            "scrollable": element.scrollable,
            "class_name": element.class_name,
        })
        if len(elements) >= _MAX_VISIBLE_ELEMENTS:
            break
    return {
        "package": observation.package,
        "activity": observation.activity,
        "revision": observation.revision,
        "elements": elements,
    }


def _history_payload(context: ReasoningContext) -> list[dict[str, Any]]:
    payload = []
    for step in context.history[-_MAX_HISTORY_STEPS:]:
        payload.append({
            "action": step.decision.action.type.value,
            "target_id": step.decision.action.target_id,
            "target_label": step.decision.target_label,
            "reason": step.decision.reason,
            "accepted": step.execution.accepted,
            "changed": step.execution.changed,
            "error": step.execution.error,
        })
    return payload


def _evidence_payload(evidence: object | None) -> dict[str, Any] | None:
    if evidence is None:
        return None
    payload: dict[str, Any] = {}
    for name in ("current_revision", "previous_revision", "last_action", "last_execution_accepted", "last_execution_changed"):
        value = getattr(evidence, name, None)
        if value is not None:
            payload[name] = value
    for name, limit in (("visible_labels", 24), ("added_labels", 12), ("removed_labels", 12),
                        ("blocking_messages", 8), ("last_consequence", 12)):
        values = getattr(evidence, name, ())
        if values:
            payload[name] = list(values)[:limit]
    hints = getattr(evidence, "action_stage_hints", ())
    if hints:
        payload["action_stage_hints"] = [{"id": i, "label": l, "stage": s} for i, l, s in hints[:12]]
    prerequisites = getattr(evidence, "unsatisfied_prerequisites", ())
    if prerequisites:
        payload["unsatisfied_prerequisites"] = list(prerequisites)[:8]
    rejected = getattr(evidence, "rejected_actions", ())
    if rejected:
        payload["rejected_actions"] = list(rejected)[-8:]
    return payload


def _goal_stage_guidance(context: ReasoningContext) -> list[dict[str, Any]]:
    stage_words = {
        "start": 1, "begin": 1, "launch": 1,
        "continue": 2, "next": 2, "proceed": 2,
        "finish": 3, "complete": 3, "done": 3, "submit": 3,
    }
    goal_words = re.findall(r"[a-z]+", context.goal.text.lower())
    stages = [stage_words[w] for w in goal_words if w in stage_words]
    if not stages:
        return []
    target_stage = max(stages)
    object_words = [w for w in goal_words if w not in stage_words]
    if not object_words:
        return []
    object_norm = " ".join(object_words)
    completed = {_normalize(s.decision.target_label) for s in context.history if s.execution.accepted and s.execution.changed and s.decision.target_label}
    candidates = []
    for element in context.observation.elements:
        if not element.visible or not element.enabled or not element.clickable:
            continue
        label = _label(element)
        if not label:
            continue
        label_norm = _normalize(label)
        if label_norm in completed:
            continue
        if object_norm not in label_norm and label_norm not in object_norm:
            continue
        label_stages = [stage_words[w] for w in re.findall(r"[a-z]+", label.lower()) if w in stage_words]
        stage = min(label_stages) if label_stages else 10 if target_stage > 10 else target_stage
        if stage < target_stage:
            candidates.append({"id": element.id, "label": label, "stage": stage})
    return candidates


def _plan_payload(context: ReasoningContext) -> dict[str, Any] | None:
    plan = context.plan
    if plan is None:
        return None
    return {
        "revision": plan.revision,
        "cursor": plan.cursor,
        "current": plan.current.description if plan.current else None,
        "remaining": [step.description for step in plan.remaining],
    }


def _reasoning_payload(context: ReasoningContext) -> dict[str, Any]:
    """Build a compact, bounded prompt so every reasoning call stays cheap."""
    plan = _plan_payload(context)
    rules = [
        "Choose one action supported by the current UI.",
        "Prefer the smallest safe action that advances the goal.",
        "Treat the plan as guidance, not proof of success.",
        "Never invent an element id; reassess after UI changes.",
    ]
    if plan is not None and plan["current"] is not None:
        rules.extend([
            "The plan's current intent is the immediate mission objective for this decision.",
            "Choose the current UI element that best advances that intent, not a later plan step.",
            "Your reason must describe the actual selected target/action.",
            "Use the selected target's current label when one exists; never call one UI element by another element's label.",
        ])
    return {
        "goal": context.goal.text,
        "rules": rules,
        "plan": plan,
        "observation": _observation_payload(context.observation),
        "evidence": _evidence_payload(context.evidence),
        "goal_stage_candidates": _goal_stage_guidance(context),
        "history": _history_payload(context),
    }


class LLMReasoner:
    def __init__(self, responder: Callable[[str], Mapping[str, Any]]):
        self._responder = responder

    def decide(self, context: ReasoningContext) -> Decision:
        prompt = json.dumps(_reasoning_payload(context), ensure_ascii=False, separators=(",", ":"))
        response = self._responder(prompt)
        return self._decision_from_response(context, response)

    def _decision_from_response(self, context: ReasoningContext, response: Mapping[str, Any]) -> Decision:
        action_name = response.get("action_type")
        try:
            action_type = ActionType(str(action_name))
        except ValueError as exc:
            raise ValueError(f"unsupported action_type: {action_name!r}") from exc
        reason = response.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason must be a non-empty string")
        reason = reason.strip()[:_MAX_REASON_LENGTH]
        target_id = response.get("target_id")
        value = response.get("value")
        target = None
        if target_id is not None:
            target = next((element for element in context.observation.elements if element.id == target_id), None)
            if target is None:
                raise ValueError(f"unknown target_id: {target_id!r}")
            if not target.visible or not target.enabled:
                raise ValueError(f"target is not currently enabled and visible: {target_id!r}")
        if action_type is ActionType.TAP:
            if target is None or not target.clickable:
                raise ValueError("tap requires a current clickable target")
        elif action_type is ActionType.TYPE:
            if target is None or not target.editable:
                raise ValueError("type requires a current editable target")
            if not isinstance(value, str):
                raise ValueError("type requires a string value")
        elif action_type in (ActionType.SCROLL, ActionType.SWIPE):
            if target is not None and not target.scrollable:
                raise ValueError("scroll/swipe target must be scrollable")
        elif action_type in (ActionType.BACK, ActionType.WAIT):
            if target_id is not None:
                raise ValueError(f"{action_type.value} does not accept target_id")
        return Decision(
            action=Action(type=action_type, target_id=target_id, value=value),
            reason=reason,
            target_label=_label(target) if target is not None else None,
        )
