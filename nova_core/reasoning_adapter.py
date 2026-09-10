"""Adapters that keep legacy and model-backed reasoning behind the v2 port."""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Mapping, Protocol

from .models import Action, ActionType, Decision, Observation
from .ports import Reasoner
from .reasoning import ReasoningContext


_STAGE_WORDS = {"start": 10, "begin": 10, "launch": 10, "continue": 20, "next": 20, "proceed": 20, "finish": 30, "complete": 30, "done": 30, "submit": 40}
_MAX_HISTORY_ITEMS = 3
_MAX_VISIBLE_LABELS = 24
_MAX_REASON_LENGTH = 160
_MAX_LEARNING_ITEMS = 4


class LegacyReasoner(Protocol):
    def decide(self, goal: str, observation: object, history: tuple) -> object: ...


class LegacyReasoningAdapter:
    def __init__(self, provider: LegacyReasoner) -> None: self._provider = provider
    def decide(self, context: ReasoningContext) -> Decision: return self._translate(self._provider.decide(context.goal.text, context.observation, context.history))
    @staticmethod
    def _translate(raw: object) -> Decision:
        if not isinstance(raw, dict): raise ValueError("legacy reasoner must return a mapping")
        action_type, target = raw.get("action_type"), raw.get("target")
        target_id = target.get("element_id") if isinstance(target, dict) else None
        reason = str(raw.get("reason", "legacy provider decision"))
        if action_type == "click":
            if not isinstance(target_id, str) or not target_id: raise ValueError("legacy click decision requires target.element_id")
            return Decision(Action(ActionType.TAP, target_id=target_id), reason)
        if action_type == "back": return Decision(Action(ActionType.BACK), reason)
        if action_type == "scroll": return Decision(Action(ActionType.SCROLL, target_id=target_id), reason)
        raise ValueError(f"unsupported legacy action type: {action_type!r}")


class LLMReasoner:
    def __init__(self, responder: Callable[[str], Mapping[str, Any]]) -> None: self._responder = responder
    def decide(self, context: ReasoningContext) -> Decision:
        prompt = json.dumps(_reasoning_payload(context), ensure_ascii=False, separators=(",", ":"))
        try: response = self._responder(prompt)
        except Exception as exc: raise RuntimeError(f"reasoning provider failed: {exc}") from exc
        if not isinstance(response, Mapping): raise ValueError("LLM response must be an object")
        return _decision_from_response(response, context)


def _label(element: Any) -> str:
    return element.text or element.content_description


def _observation_payload(observation: Observation) -> dict[str, Any]:
    """Serialize only information useful for selecting the next action."""
    elements = []
    visible_labels = []
    for element in observation.elements:
        if not element.visible:
            continue
        label = _label(element)
        if label and len(visible_labels) < _MAX_VISIBLE_LABELS:
            visible_labels.append(label)
        actionable = element.enabled and (element.clickable or element.editable or element.scrollable)
        if not actionable:
            continue
        item = {"id": element.id, "label": label or None}
        if element.clickable: item["tap"] = True
        if element.editable: item["type"] = True
        if element.scrollable: item["scroll"] = True
        if element.checkable: item["checked"] = element.checked
        if element.focused: item["focused"] = True
        elements.append(item)
    return {"package": observation.package, "activity": observation.activity, "revision": observation.revision,
            "actions": elements, "visible_labels": visible_labels}


def _observation_history_summary(observation: Observation | None) -> dict[str, Any] | None:
    if observation is None: return None
    labels = [_label(e) for e in observation.elements if e.visible and _label(e)]
    return {"revision": observation.revision, "labels": labels[:_MAX_VISIBLE_LABELS]}


def _normalize(text: str) -> str: return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def _goal_stage_guidance(context: ReasoningContext) -> list[dict[str, Any]]:
    goal_words = re.findall(r"[a-z]+", context.goal.text.lower())
    stages = [_STAGE_WORDS[w] for w in goal_words if w in _STAGE_WORDS]
    if not stages: return []
    target_stage = max(stages)
    object_words = [w for w in goal_words if w not in _STAGE_WORDS]
    if not object_words: return []
    object_norm = " ".join(object_words)
    completed = {_normalize(s.decision.target_label) for s in context.history if s.execution.accepted and s.execution.changed and s.decision.target_label}
    candidates = []
    for element in context.observation.elements:
        if not element.visible or not element.enabled or not element.clickable: continue
        label = _label(element)
        if not label: continue
        label_norm = _normalize(label)
        if label_norm in completed: continue
        if object_norm not in label_norm and label_norm not in object_norm: continue
        label_stages = [_STAGE_WORDS[w] for w in re.findall(r"[a-z]+", label.lower()) if w in _STAGE_WORDS]
        stage = min(label_stages) if label_stages else 10 if target_stage > 10 else target_stage
        if stage < target_stage:
            candidates.append({"id": element.id, "label": label, "stage": stage})
    return candidates


def _evidence_payload(evidence: object | None) -> dict[str, Any] | None:
    if evidence is None: return None
    payload: dict[str, Any] = {}
    for name in ("current_revision", "previous_revision", "last_action", "last_execution_accepted", "last_execution_changed", "observation_changed", "unchanged_observation_count"):
        value = getattr(evidence, name, None)
        if value is not None: payload[name] = value
    for name, limit in (("visible_labels", _MAX_VISIBLE_LABELS), ("added_labels", 12), ("removed_labels", 12),
                        ("blocking_messages", 8), ("last_consequence", 12)):
        values = getattr(evidence, name, ())
        if values: payload[name] = list(values)[:limit]
    hints = getattr(evidence, "action_stage_hints", ())
    if hints: payload["action_stage_hints"] = [{"id": i, "label": l, "stage": s} for i, l, s in hints[:12]]
    prerequisites = getattr(evidence, "unsatisfied_prerequisites", ())
    if prerequisites:
        payload["unsatisfied_prerequisites"] = [{"id": i, "label": l, "required": r, "stage": s} for i, l, r, s in prerequisites[:8]]
    rejected = getattr(evidence, "rejected_actions", ())
    if rejected:
        payload["rejected_actions"] = [{"action": t, "target": target, "error": error[:_MAX_REASON_LENGTH]} for t, target, error in rejected[-4:]]
    return payload


def _learning_payload(context: ReasoningContext) -> dict[str, Any]:
    """Summarize recent outcomes so reasoning can adapt instead of blindly repeating."""
    attempts = []
    counts: dict[tuple[str, str | None], int] = {}
    for step in context.history[-_MAX_HISTORY_ITEMS:]:
        if step.execution.accepted and not step.execution.changed:
            key = (step.decision.action.type.value, step.decision.action.target_id)
            counts[key] = counts.get(key, 0) + 1
            item: dict[str, Any] = {"action": key[0], "target": key[1], "label": step.decision.target_label or None}
            if step.execution.error:
                item["error"] = step.execution.error[:_MAX_REASON_LENGTH]
            attempts.append(item)
    repeated = [
        {"action": action, "target": target, "attempts": count}
        for (action, target), count in counts.items()
        if count > 1
    ]
    return {
        "accepted_but_no_progress": attempts[-_MAX_LEARNING_ITEMS:],
        "repeated_ineffective_actions": repeated[-_MAX_LEARNING_ITEMS:],
        "guidance": "Treat ineffective outcomes as evidence. Do not repeat an accepted action with no progress unless the current observation provides a concrete reason it may now work.",
    }


def _recovery_payload(context: ReasoningContext) -> dict[str, Any]:
    """Expose bounded alternatives when recent evidence says the current strategy failed."""
    ineffective = []
    ineffective_targets = set()
    for step in context.history[-_MAX_HISTORY_ITEMS:]:
        if step.execution.accepted and not step.execution.changed:
            target = step.decision.action.target_id
            key = (step.decision.action.type.value, target)
            ineffective.append({
                "action": key[0],
                "target": target,
                "label": step.decision.target_label or None,
                "error": (step.execution.error or "")[:_MAX_REASON_LENGTH],
            })
            ineffective_targets.add(key)

    alternatives = []
    for element in context.observation.elements:
        if not element.visible or not element.enabled:
            continue
        label = _label(element)
        if not label:
            continue
        if element.clickable and (ActionType.TAP.value, element.id) not in ineffective_targets:
            alternatives.append({"action": ActionType.TAP.value, "target": element.id, "label": label})
        if element.editable and (ActionType.TYPE.value, element.id) not in ineffective_targets:
            alternatives.append({"action": ActionType.TYPE.value, "target": element.id, "label": label})
        if element.scrollable and (ActionType.SCROLL.value, element.id) not in ineffective_targets:
            alternatives.append({"action": ActionType.SCROLL.value, "target": element.id, "label": label})
        if len(alternatives) >= _MAX_LEARNING_ITEMS:
            break

    if not ineffective:
        return {"active": False}
    return {
        "active": True,
        "ineffective_recent_actions": ineffective[-_MAX_LEARNING_ITEMS:],
        "available_alternatives": alternatives[:_MAX_LEARNING_ITEMS],
        "guidance": "Change strategy after ineffective progress. Select an alternative only when it is supported by the current observation and advances the goal. Do not retry the failed target without new evidence.",
    }


def _history_payload(context: ReasoningContext) -> list[dict[str, Any]]:
    """Keep only recent, decision-relevant history to prevent prompt growth."""
    result = []
    for step in context.history[-_MAX_HISTORY_ITEMS:]:
        item: dict[str, Any] = {"action": step.decision.action.type.value, "target": step.decision.action.target_id,
                                "value": step.decision.action.value, "accepted": step.execution.accepted,
                                "changed": step.execution.changed}
        if step.execution.error: item["error"] = step.execution.error[:_MAX_REASON_LENGTH]
        if step.decision.target_label: item["label"] = step.decision.target_label
        if step.decision.plan_stale: item["plan_stale"] = True
        if step.post_observation is not None: item["after"] = _observation_history_summary(step.post_observation)
        result.append(item)
    return result


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


def _mission_payload(context: ReasoningContext) -> dict[str, Any] | None:
    if context.mission_state is None:
        return None
    return context.mission_state.reasoning_snapshot()


def _reasoning_payload(context: ReasoningContext) -> dict[str, Any]:
    """Build a compact, bounded prompt so every reasoning call stays cheap."""
    plan = _plan_payload(context)
    mission = _mission_payload(context)
    rules = [
        "Choose one action supported by the current UI.",
        "Prefer the smallest safe action that advances the goal.",
        "Treat the plan as guidance, not proof of success.",
        "Never invent an element id; reassess after UI changes.",
        "Use mission state only as evidence of what has happened.",
        "The current observation is authoritative for what is available now.",
        "If the remaining plan no longer fits the current observation or mission state, set plan_status to stale instead of forcing an action to satisfy the old plan.",
        "Use plan_status valid when the remaining plan still makes sense from the current state.",
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
        "mission": mission,
        "plan": plan,
        "observation": _observation_payload(context.observation),
        "evidence": _evidence_payload(context.evidence),
        "learning": _learning_payload(context),
        "recovery": _recovery_payload(context),
        "goal_stage_candidates": _goal_stage_guidance(context),
        "history": _history_payload(context),
    }


def _decision_from_response(response: Mapping[str, Any], context: ReasoningContext) -> Decision:
    action_type = response.get("action_type")
    try: action = ActionType(action_type)
    except (TypeError, ValueError) as exc: raise ValueError("invalid action_type") from exc
    target_id, value, reason = response.get("target_id"), response.get("value"), str(response.get("reason", "model decision"))
    plan_status = response.get("plan_status", "valid")
    if plan_status not in ("valid", "stale"):
        raise ValueError("plan_status must be 'valid' or 'stale'")
    plan_stale = plan_status == "stale"
    if target_id is not None and (not isinstance(target_id, str) or not target_id): raise ValueError("target_id must be a non-empty string or null")
    if value is not None and not isinstance(value, str): raise ValueError("value must be a string or null")
    if action in (ActionType.BACK, ActionType.WAIT):
        if target_id is not None or value is not None: raise ValueError("target_id and value are not allowed for this action")
        return Decision(Action(action), reason, plan_stale=plan_stale)
    if action is ActionType.TAP:
        if target_id is None or value is not None: raise ValueError("tap requires target_id and no value")
        element = next((item for item in context.observation.elements if item.id == target_id), None)
        if element is None or not element.visible or not element.enabled or not element.clickable: raise ValueError("tap target is not available in the current observation")
        return Decision(Action(action, target_id=target_id), reason, target_label=_label(element), plan_stale=plan_stale)
    if action is ActionType.SCROLL:
        if target_id is not None:
            element = next((item for item in context.observation.elements if item.id == target_id), None)
            if element is None or not element.visible or not element.enabled or not element.scrollable: raise ValueError("scroll target is not available in the current observation")
        return Decision(Action(action, target_id=target_id), reason, plan_stale=plan_stale)
    if action is ActionType.TYPE:
        if target_id is None or value is None: raise ValueError("type requires target_id and value")
        element = next((item for item in context.observation.elements if item.id == target_id), None)
        if element is None or not element.visible or not element.enabled or not element.editable: raise ValueError("type target is not available in the current observation")
        return Decision(Action(action, target_id=target_id, value=value), reason, target_label=_label(element), plan_stale=plan_stale)
    if action is ActionType.SWIPE:
        if target_id is None or value is None: raise ValueError("swipe requires target_id and value")
        element = next((item for item in context.observation.elements if item.id == target_id), None)
        if element is None or not element.visible or not element.enabled: raise ValueError("swipe target is not available in the current observation")
        return Decision(Action(action, target_id=target_id, value=value), reason, target_label=_label(element), plan_stale=plan_stale)
    raise ValueError("unsupported action type")
