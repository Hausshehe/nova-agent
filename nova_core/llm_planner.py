"""Strict, provider-neutral LLM mission planning for Nova Agent v2."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from typing import Callable, Protocol

from .planning import Plan, PlanStep
from .reasoning import ReasoningContext


_MAX_PLAN_STEPS = 8
_FORBIDDEN_INTENT_PATTERNS = (
    r"\bwait for\b",
    r"\bcheck if\b",
    r"\bcheck whether\b",
    r"\bdecide what to do\b",
    r"\bif no progress\b",
    r"\bif .*\bthen\b",
    r"\bwhen .*\bthen\b",
)
_STAGE_WORDS = {"start": 10, "begin": 10, "launch": 10, "continue": 20, "next": 20, "proceed": 20, "finish": 30, "complete": 30, "done": 30, "submit": 40}


class PlannerTransport(Protocol):
    """Minimal text-completion capability required by the LLM planner."""

    def complete(self, prompt: str) -> str:
        ...


@dataclass(frozen=True)
class PlanStep:
    """One bounded intent in a mission plan, not a concrete UI action."""

    description: str


class LLMPlanner:
    """Turn runtime evidence into a bounded sequence of mission intents.

    The planner never creates concrete UI actions. The action reasoner remains
    responsible for selecting an executable action from the current
    observation. This keeps planning useful without giving model output direct
    execution authority.
    """

    def __init__(self, complete: Callable[[str], str] | PlannerTransport, *, max_steps: int = _MAX_PLAN_STEPS) -> None:
        if max_steps < 1 or max_steps > _MAX_PLAN_STEPS:
            raise ValueError(f"max_steps must be between 1 and {_MAX_PLAN_STEPS}")
        self._complete = complete.complete if hasattr(complete, "complete") else complete
        self.max_steps = max_steps

    def plan(self, context: ReasoningContext) -> Plan:
        payload = self._request(context, previous=None)
        return Plan(self._ground_steps(self._parse_steps(payload), context), revision=0)

    def replan(self, context: ReasoningContext, previous: Plan) -> Plan:
        payload = self._request(context, previous=previous)
        return Plan(self._ground_steps(self._parse_steps(payload), context), revision=previous.revision + 1)

    def _goal_stage_candidates(self, context: ReasoningContext) -> tuple[str, ...]:
        """Find strong current-UI candidates implied by staged goal language.

        This is deliberately narrow. It is not a hard-coded task sequence. It
        only constrains planning when the current observation contains an
        enabled clickable element whose label directly matches the goal object
        and whose stage is earlier than the requested completion stage.
        """
        goal_words = re.findall(r"[a-z]+", context.goal.text.lower())
        stages = [_STAGE_WORDS[word] for word in goal_words if word in _STAGE_WORDS]
        if not stages:
            return ()
        target_stage = max(stages)
        object_words = [word for word in goal_words if word not in _STAGE_WORDS]
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
            label_stages = [_STAGE_WORDS[word] for word in re.findall(r"[a-z]+", label.lower()) if word in _STAGE_WORDS]
            stage = min(label_stages) if label_stages else 10 if target_stage > 10 else target_stage
            if stage < target_stage:
                candidates.append((stage, label))
        candidates.sort(key=lambda item: (item[0], item[1].casefold()))
        return tuple(label for _, label in candidates)

    def _ground_steps(self, steps: tuple[PlanStep, ...], context: ReasoningContext) -> tuple[PlanStep, ...]:
        """Prevent a model from ignoring a strong goal-relevant current UI candidate."""
        candidates = self._goal_stage_candidates(context)
        if not candidates or not steps:
            return steps
        first = steps[0].description
        first_norm = " ".join(re.findall(r"[a-z0-9]+", first.lower()))
        if any(" ".join(re.findall(r"[a-z0-9]+", candidate.lower())) in first_norm for candidate in candidates):
            return steps
        grounded = (PlanStep(candidates[0]),) + steps[1:]
        return grounded

    def _request(self, context: ReasoningContext, previous: Plan | None) -> str:
        observation = {
            "package": context.observation.package,
            "activity": context.observation.activity,
            "revision": context.observation.revision,
            "elements": [
                {
                    "id": element.id,
                    "text": element.text,
                    "content_description": element.content_description,
                    "clickable": element.clickable,
                    "enabled": element.enabled,
                    "editable": element.editable,
                    "scrollable": element.scrollable,
                    "visible": element.visible,
                }
                for element in context.observation.elements
            ],
        }
        if context.evidence is None:
            evidence = None
        elif is_dataclass(context.evidence):
            evidence = asdict(context.evidence)
        else:
            evidence = repr(context.evidence)
        learning = {
            "relevant_records": [record.snapshot() for record in context.relevant_learning],
            "lessons": [lesson.snapshot() for lesson in context.learning_assessment.lessons]
            if context.learning_assessment is not None
            else [],
            "warnings": list(context.learning_assessment.warnings)
            if context.learning_assessment is not None
            else [],
            "guidance": list(context.learning_assessment.guidance)
            if context.learning_assessment is not None
            else [],
        }
        uncertainty = context.uncertainty
        uncertainty_payload = uncertainty.snapshot() if uncertainty is not None else {
            "level": "unknown",
            "basis": "uncertainty was not supplied",
            "unknowns": [],
            "conflicts": [],
        }
        uncertainty_mode = {
            "high": "reassess",
            "medium": "progress_check",
            "low": "execute",
        }.get(uncertainty_payload["level"], "reassess")
        previous_text = (
            [step.description for step in previous.remaining]
            if previous is not None
            else [step.description for step in context.plan.remaining]
            if context.plan is not None
            else []
        )
        goal_stage_candidates = self._goal_stage_candidates(context)
        prompt = (
            "You are Nova's mission planner. Produce a short sequence of executable mission intents, "
            "not UI actions and not internal control-flow commentary. The action reasoner will choose "
            "concrete UI actions later. Every intent must describe a concrete goal-directed piece of work "
            "that the reasoner can execute from the current observation. Do not output meta-steps such as "
            "'wait for observable change', 'check if progress made', 'decide what to do', or conditional "
            "instructions such as 'if no progress, ...'. Encode the intended recovery action itself as a "
            "step. Do not invent a recovery branch merely because one exists in the app: recovery intents "
            "must be supported by current evidence of failure, rejection, or stalled progress. Historical "
            "lessons are warnings only: current observation and evidence take priority, and a lesson must "
            "never be treated as proof that an action is valid now.\n"
            "The first intent must be grounded in the current observation. When GOAL_STAGE_CANDIDATES is "
            "non-empty, the first intent MUST advance one of those candidates. Do not select an unrelated "
            "clickable control merely because it is visible. These candidates are derived from the current "
            "UI and goal language, not from a hard-coded task sequence.\n"
            "Uncertainty is behavioral guidance, not decoration. If uncertainty is high, do not assume the "
            "previous action worked or that the goal is closer to completion; prefer a concrete intent that "
            "resolves an unknown or produces fresh observable evidence, and do not repeat an ineffective "
            "action without new evidence. If uncertainty is medium, prefer a concrete goal-advancing intent "
            "whose effect can be verified from a fresh observation. If uncertainty is low, proceed normally "
            "while still requiring evidence-backed completion. Conflicting evidence must remain unresolved "
            "rather than being silently ignored.\n"
            "Return ONLY valid JSON in this exact shape: {\"steps\":[\"intent\", ...]}.\n"
            f"Use at most {self.max_steps} steps. Each intent must be a non-empty string.\n"
            f"GOAL: {context.goal.text}\n"
            f"OBSERVATION: {json.dumps(observation, ensure_ascii=False, separators=(',', ':'))}\n"
            f"GOAL_STAGE_CANDIDATES: {json.dumps(list(goal_stage_candidates), ensure_ascii=False)}\n"
            f"EVIDENCE: {json.dumps(evidence, ensure_ascii=False, separators=(',', ':'))}\n"
            f"UNCERTAINTY: {json.dumps({**uncertainty_payload, 'mode': uncertainty_mode}, ensure_ascii=False, separators=(',', ':'))}\n"
            f"LEARNING: {json.dumps(learning, ensure_ascii=False, separators=(',', ':'))}\n"
            f"PREVIOUS_PLAN_REMAINING: {json.dumps(previous_text, ensure_ascii=False)}\n"
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
