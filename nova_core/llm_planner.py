"""Strict, provider-neutral LLM mission planning for Nova Agent v2."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from typing import Any, Callable, Protocol

from .planning import Plan, PlanStep
from .reasoning import ReasoningContext


_MAX_PLAN_STEPS = 8
_MAX_OBSERVATION_ACTIONS = 24
_MAX_VISIBLE_LABELS = 24
_MAX_LEARNING_ITEMS = 4
_MAX_EVIDENCE_ITEMS = 12
_MAX_TEXT_LENGTH = 240
_FORBIDDEN_INTENT_PATTERNS = (
    r"\bwait for\b", r"\bcheck if\b", r"\bcheck whether\b",
    r"\bdecide what to do\b", r"\bif no progress\b", r"\bif .*\bthen\b",
    r"\bwhen .*\bthen\b",
)
_STAGE_WORDS = {"start": 10, "begin": 10, "launch": 10, "continue": 20, "next": 20, "proceed": 20, "finish": 30, "complete": 30, "done": 30, "submit": 40}


class PlannerTransport(Protocol):
    def complete(self, prompt: str) -> str: ...


class LLMPlanner:
    """Turn runtime evidence into bounded mission intents, never concrete UI actions."""

    def __init__(self, complete: Callable[[str], str] | PlannerTransport, *, max_steps: int = _MAX_PLAN_STEPS) -> None:
        if max_steps < 1 or max_steps > _MAX_PLAN_STEPS:
            raise ValueError(f"max_steps must be between 1 and {_MAX_PLAN_STEPS}")
        self._complete = complete.complete if hasattr(complete, "complete") else complete
        self.max_steps = max_steps

    def plan(self, context: ReasoningContext) -> Plan:
        return Plan(self._ground_steps(self._parse_steps(self._request(context, None)), context), revision=0)

    def replan(self, context: ReasoningContext, previous: Plan) -> Plan:
        return Plan(self._ground_steps(self._parse_steps(self._request(context, previous)), context), revision=previous.revision + 1)

    def _goal_stage_candidates(self, context: ReasoningContext) -> tuple[str, ...]:
        goal_words = re.findall(r"[a-z]+", context.goal.text.lower())
        stages = [_STAGE_WORDS[w] for w in goal_words if w in _STAGE_WORDS]
        if not stages:
            return ()
        target_stage = max(stages)
        object_words = [w for w in goal_words if w not in _STAGE_WORDS]
        if not object_words:
            return ()
        object_norm = " ".join(object_words)
        candidates: list[tuple[int, str]] = []
        for element in context.observation.elements:
            if not element.visible or not element.enabled or not element.clickable:
                continue
            label = element.text or element.content_description
            if not label:
                continue
            label_norm = " ".join(re.findall(r"[a-z0-9]+", label.lower()))
            if object_norm not in label_norm and label_norm not in object_norm:
                continue
            label_stages = [_STAGE_WORDS[w] for w in re.findall(r"[a-z]+", label.lower()) if w in _STAGE_WORDS]
            stage = min(label_stages) if label_stages else 10 if target_stage > 10 else target_stage
            if stage < target_stage:
                candidates.append((stage, label))
        candidates.sort(key=lambda item: (item[0], item[1].casefold()))
        return tuple(label for _, label in candidates)

    def _ground_steps(self, steps: tuple[PlanStep, ...], context: ReasoningContext) -> tuple[PlanStep, ...]:
        candidates = self._goal_stage_candidates(context)
        if not candidates or not steps:
            return steps
        first_norm = " ".join(re.findall(r"[a-z0-9]+", steps[0].description.lower()))
        if any(" ".join(re.findall(r"[a-z0-9]+", candidate.lower())) in first_norm for candidate in candidates):
            return steps
        return (PlanStep(candidates[0]),) + steps[1:]

    @staticmethod
    def _observation_payload(context: ReasoningContext) -> dict[str, Any]:
        """Keep planner context focused on the current actionable UI."""
        actions, labels = [], []
        for element in context.observation.elements:
            if not element.visible:
                continue
            label = element.text or element.content_description
            if label and len(labels) < _MAX_VISIBLE_LABELS:
                labels.append(label)
            if not (element.enabled and (element.clickable or element.editable or element.scrollable)):
                continue
            if len(actions) >= _MAX_OBSERVATION_ACTIONS:
                continue
            item: dict[str, Any] = {"id": element.id, "label": label or None}
            if element.clickable: item["tap"] = True
            if element.editable: item["type"] = True
            if element.scrollable: item["scroll"] = True
            actions.append(item)
        return {"package": context.observation.package, "activity": context.observation.activity,
                "revision": context.observation.revision, "actions": actions, "visible_labels": labels}

    @staticmethod
    def _bounded_evidence(context: ReasoningContext) -> Any:
        evidence = context.evidence
        if evidence is None:
            return None
        if is_dataclass(evidence):
            payload = asdict(evidence)
            for key in ("visible_labels", "added_labels", "removed_labels", "blocking_messages", "last_consequence"):
                if isinstance(payload.get(key), list):
                    payload[key] = payload[key][:_MAX_EVIDENCE_ITEMS]
            if isinstance(payload.get("rejected_actions"), list):
                payload["rejected_actions"] = payload["rejected_actions"][-_MAX_EVIDENCE_ITEMS:]
            return payload
        return repr(evidence)[:_MAX_TEXT_LENGTH]

    @staticmethod
    def _bounded_learning(context: ReasoningContext) -> dict[str, Any]:
        assessment = context.learning_assessment
        return {
            "relevant_records": [r.snapshot() for r in context.relevant_learning[:_MAX_LEARNING_ITEMS]],
            "lessons": [l.snapshot() for l in assessment.lessons[:_MAX_LEARNING_ITEMS]] if assessment is not None else [],
            "warnings": list(assessment.warnings[:_MAX_LEARNING_ITEMS]) if assessment is not None else [],
            "guidance": list(assessment.guidance[:_MAX_LEARNING_ITEMS]) if assessment is not None else [],
        }

    def _request(self, context: ReasoningContext, previous: Plan | None) -> str:
        uncertainty = context.uncertainty
        uncertainty_payload = uncertainty.snapshot() if uncertainty is not None else {
            "level": "unknown", "basis": "uncertainty was not supplied", "unknowns": [], "conflicts": [],
        }
        uncertainty_mode = {"high": "reassess", "medium": "progress_check", "low": "execute"}.get(uncertainty_payload["level"], "reassess")
        previous_text = [step.description for step in previous.remaining] if previous is not None else (
            [step.description for step in context.plan.remaining] if context.plan is not None else []
        )
        candidates = self._goal_stage_candidates(context)
        prompt = (
            "You are Nova's mission planner. Produce a short sequence of executable mission intents, not UI actions. "
            "The action reasoner selects concrete actions from the current observation. Every intent must be concrete "
            "and goal-directed. Never output wait/check/decide/conditional control-flow steps. Encode recovery itself "
            "as an intent only when current evidence supports failure or stalled progress. Historical lessons are "
            "warnings, not proof. Current observation and evidence take priority.\n"
            "Ground the first intent in the current observation. If GOAL_STAGE_CANDIDATES is non-empty, the first "
            "intent MUST advance one of them. High uncertainty means reassess and resolves an unknown; medium means "
            "choose a verifiable action whose effect can be verified from a fresh observation; low means proceed normally. "
            "Conflicting evidence must remain unresolved until current evidence supports a resolution.\n"
            "Return ONLY JSON: {\"steps\":[\"intent\", ...]}.\n"
            f"Use at most {self.max_steps} steps.\n"
            f"GOAL: {context.goal.text}\n"
            f"OBSERVATION: {json.dumps(self._observation_payload(context), ensure_ascii=False, separators=(',', ':'))}\n"
            f"GOAL_STAGE_CANDIDATES: {json.dumps(list(candidates), ensure_ascii=False)}\n"
            f"EVIDENCE: {json.dumps(self._bounded_evidence(context), ensure_ascii=False, separators=(',', ':'))}\n"
            f"UNCERTAINTY: {json.dumps({**uncertainty_payload, 'mode': uncertainty_mode}, ensure_ascii=False, separators=(',', ':'))}\n"
            f"LEARNING: {json.dumps(self._bounded_learning(context), ensure_ascii=False, separators=(',', ':'))}\n"
            f"PREVIOUS_PLAN_REMAINING: {json.dumps(previous_text[:_MAX_PLAN_STEPS], ensure_ascii=False)}\n"
        )
        return self._complete(prompt)

    def _parse_steps(self, response: str) -> tuple[PlanStep, ...]:
        try:
            data = json.loads(response)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"planner returned invalid JSON: {exc}") from exc
        if not isinstance(data, dict) or set(data) != {"steps"}:
            raise ValueError("planner response must contain only a steps field")
        steps = data["steps"]
        if not isinstance(steps, list) or not steps:
            raise ValueError("planner steps must be a non-empty list")
        if len(steps) > self.max_steps:
            raise ValueError(f"planner returned more than {self.max_steps} steps")
        normalized: list[PlanStep] = []
        previous_normalized: str | None = None
        for step in steps:
            if not isinstance(step, str) or not step.strip():
                raise ValueError("planner steps must be non-empty strings")
            normalized_text = " ".join(step.split())
            lowered = normalized_text.casefold()
            if any(re.search(pattern, lowered) for pattern in _FORBIDDEN_INTENT_PATTERNS):
                raise ValueError(f"planner returned meta/control-flow intent: {normalized_text!r}")
            if previous_normalized == lowered:
                raise ValueError(f"planner returned duplicate consecutive intent: {normalized_text!r}")
            normalized.append(PlanStep(normalized_text))
            previous_normalized = lowered
        return tuple(normalized)
