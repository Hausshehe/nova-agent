"""Strict, provider-neutral LLM mission planning for Nova Agent v2."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Callable, Protocol

from .planning import Plan, PlanStep
from .reasoning import ReasoningContext


_MAX_PLAN_STEPS = 8


class PlannerTransport(Protocol):
    """Minimal text-completion capability required by the LLM planner."""

    def complete(self, prompt: str) -> str:
        ...


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
        return Plan(self._parse_steps(payload), revision=0)

    def replan(self, context: ReasoningContext, previous: Plan) -> Plan:
        payload = self._request(context, previous=previous)
        return Plan(self._parse_steps(payload), revision=previous.revision + 1)

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
        previous_text = (
            [step.description for step in previous.remaining]
            if previous is not None
            else [step.description for step in context.plan.remaining]
            if context.plan is not None
            else []
        )
        prompt = (
            "You are Nova's mission planner. Produce a short sequence of executable mission intents, "
            "not UI actions and not internal control-flow commentary. The action reasoner will choose "
            "concrete UI actions later. Every intent must describe a concrete goal-directed piece of work "
            "that the reasoner can execute from the current observation. Do not output meta-steps such as "
            "'wait for observable change', 'check if progress made', 'decide what to do', or conditional "
            "instructions such as 'if no progress, ...'. Encode the intended recovery action itself as a "
            "step.\n"
            "Return ONLY valid JSON in this exact shape: {\"steps\":[\"intent\", ...]}.\n"
            f"Use at most {self.max_steps} steps. Each intent must be a non-empty string.\n"
            f"GOAL: {context.goal.text}\n"
            f"OBSERVATION: {json.dumps(observation, ensure_ascii=False, separators=(',', ':'))}\n"
            f"EVIDENCE: {json.dumps(evidence, ensure_ascii=False, separators=(',', ':'))}\n"
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
        for step in steps:
            if not isinstance(step, str) or not step.strip():
                raise ValueError("planner steps must be non-empty strings")
            normalized.append(PlanStep(step.strip()))
        return tuple(normalized)
