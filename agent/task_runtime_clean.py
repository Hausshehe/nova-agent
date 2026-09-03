from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from .core import Action, ActionType, Decision, ExecutionResult, WorldState
from .goal_evaluator import GoalEvaluator
from .navigation import NavigationBridge
from .reasoning_context import build_reasoning_context


@dataclass(frozen=True)
class BlockedAction:
    action_type: ActionType
    target_id: str | None
    evidence: str
    state_key: tuple[Any, ...]

    def matches(self, action: Action, state_key: tuple[Any, ...]) -> bool:
        return (
            self.action_type is action.type
            and self.target_id == (action.target.element_id if action.target else None)
            and self.state_key == state_key
        )


@dataclass
class RuntimeState:
    blocked: list[BlockedAction] = field(default_factory=list)
    history: list[Mapping[str, Any]] = field(default_factory=list)

    def reset(self) -> None:
        self.blocked.clear()
        self.history.clear()


_FAILURE_RE = re.compile(
    r"\b(?:must|need(?:s)?|requires?|unable|cannot|can't|not allowed|not permitted|invalid|failed|failure|error|denied)\b"
    r"|\b(?:start|do|complete|finish|perform|select|choose)\b.+\bfirst\b",
    re.IGNORECASE,
)
_COMPLETION_RE = re.compile(
    r"\b(?:completed|complete|finished|success(?:ful)?|done)\b",
    re.IGNORECASE,
)


def _ui_key(state: WorldState) -> tuple[Any, ...]:
    return (state.package, state.activity, tuple(state.elements))


def _status_evidence(state: WorldState) -> str | None:
    for element in state.elements:
        if element.clickable:
            continue
        text = " ".join(p for p in (element.text, element.content_description) if p).strip()
        if text and _FAILURE_RE.search(text):
            return text
    return None


@dataclass
class CleanTaskRuntime:
    """One authoritative observe -> reason -> execute -> observe loop."""

    bridge: NavigationBridge
    planner: Any
    evaluator: GoalEvaluator = field(default_factory=GoalEvaluator)
    max_steps: int = 5
    settle_timeout: float = 2.0
    runtime_state: RuntimeState = field(default_factory=RuntimeState, init=False)
    current_state: WorldState | None = field(default=None, init=False)

    def _is_action_goal(self, goal: str) -> bool:
        words = set(re.findall(r"[a-z0-9]+", goal.lower()))
        return bool(words & {"tap", "click", "open"})

    def _action_completed(self, goal: str, decision: Decision, before: WorldState, after: WorldState) -> bool:
        if not self._is_action_goal(goal) or decision.action.type is not ActionType.CLICK:
            return False
        target = decision.action.target
        if target is None:
            return False

        before_target = next((e for e in before.elements if e.id == target.element_id), None)
        after_target = next((e for e in after.elements if e.id == target.element_id), None)

        if before_target is not None and after_target is None:
            return True

        if after_target is not None:
            after_text = " ".join(
                p for p in (after_target.text, after_target.content_description) if p
            ).strip()
            if _COMPLETION_RE.search(after_text):
                if before_target is None:
                    return False
                before_text = " ".join(
                    p for p in (before_target.text, before_target.content_description) if p
                ).strip()
                return after_text != before_text

        for e in after.elements:
            if e.clickable:
                continue
            text = " ".join(p for p in (e.text, e.content_description) if p).lower()
            if _COMPLETION_RE.search(text):
                return True
        return False

    def _guard(self, action: Action, state: WorldState) -> str | None:
        key = _ui_key(state)
        for blocked in self.runtime_state.blocked:
            if blocked.matches(action, key):
                return blocked.evidence
        return None

    def _record(self, step: int, decision: Decision, result: ExecutionResult, effect: str, evidence: str = "") -> None:
        self.runtime_state.history.append({
            "step": step,
            "target_id": decision.action.target.element_id if decision.action.target else None,
            "target_text": decision.action.target.text if decision.action.target else "",
            "action_type": decision.action.type.value,
            "accepted": result.accepted,
            "changed": result.changed,
            "verified": result.verified,
            "error": result.error,
            "task_effect": effect,
            "effect_evidence": evidence,
        })

    def run(self, goal: str) -> bool:
        self.runtime_state.reset()
        self.current_state = self.bridge.observe()
        state = self.current_state

        if not self._is_action_goal(goal) and self.evaluator.evaluate(goal, state):
            return True

        for step in range(1, self.max_steps + 1):
            context = build_reasoning_context(goal, state, self.runtime_state.history)
            try:
                decision = self.planner.decide(context) if hasattr(self.planner, "decide") else self.planner.plan(context)
            except Exception as exc:
                self.runtime_state.history.append({
                    "step": step,
                    "target_id": None,
                    "target_text": "",
                    "action_type": "invalid",
                    "accepted": False,
                    "changed": False,
                    "verified": False,
                    "error": f"reasoning error: {type(exc).__name__}: {exc}",
                    "task_effect": "failed",
                    "effect_evidence": "invalid reasoning decision",
                })
                return False

            blocked_evidence = self._guard(decision.action, state)
            if blocked_evidence is not None:
                self._record(
                    step,
                    decision,
                    ExecutionResult(False, False, False, "action blocked by runtime"),
                    "blocked",
                    blocked_evidence,
                )
                return False

            try:
                result = self.bridge.execute(decision.action)
            except Exception as exc:
                result = ExecutionResult(False, False, False, f"execution error: {type(exc).__name__}: {exc}")

            if not result.accepted:
                self._record(step, decision, result, "failed", result.error or "action rejected")
                state = self._fresh_or_current(state)
                continue

            try:
                after = self.bridge.wait_for_fresh_observation(state, self.settle_timeout)
            except TimeoutError as exc:
                self._record(
                    step,
                    decision,
                    ExecutionResult(True, False, False, str(exc)),
                    "unknown",
                    str(exc),
                )
                state = self.bridge.observe()
                self.current_state = state
                continue

            changed = _ui_key(after) != _ui_key(state)
            result = ExecutionResult(True, changed, changed, result.error)
            failure = _status_evidence(after)

            if failure:
                self.runtime_state.blocked.append(
                    BlockedAction(
                        decision.action.type,
                        decision.action.target.element_id if decision.action.target else None,
                        failure,
                        _ui_key(after),
                    )
                )
                self._record(step, decision, result, "blocked", failure)
            elif self._is_action_goal(goal):
                if self._action_completed(goal, decision, state, after):
                    self._record(step, decision, result, "completed")
                    state = after
                    self.current_state = after
                    return True
                elif changed:
                    self._record(step, decision, result, "progressed")
                else:
                    self._record(step, decision, result, "unknown", "no observable UI change")
            elif self.evaluator.evaluate(goal, after):
                self._record(step, decision, result, "completed")
                state = after
                self.current_state = after
                return True
            elif changed:
                self._record(step, decision, result, "progressed")
            else:
                self._record(step, decision, result, "unknown", "no observable UI change")

            state = after
            self.current_state = after

            current_key = _ui_key(state)
            self.runtime_state.blocked = [b for b in self.runtime_state.blocked if b.state_key == current_key]

        return False

    def _fresh_or_current(self, previous: WorldState) -> WorldState:
        try:
            state = self.bridge.observe()
        except Exception:
            state = previous
        self.current_state = state
        return state
