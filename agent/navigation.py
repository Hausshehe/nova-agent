from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol

from .core import Action, ActionType, Decision, ExecutionResult, TransitionVerifier, WorldState
from .goal_evaluator import GoalEvaluator
from .reasoning_context import ReasoningContext, build_reasoning_context
from .reasoning_provider import ReasoningProvider
from .task_effect import TaskEffectEvaluator


class NavigationBridge(Protocol):
    def observe(self) -> WorldState: ...
    def execute(self, action: Action) -> ExecutionResult: ...
    def wait_for_fresh_observation(self, previous: WorldState, timeout: float) -> WorldState: ...


class LegacyPlanner(Protocol):
    """Backward-compatible interface for pre-provider planners."""

    def plan(self, context: ReasoningContext) -> Decision: ...


def _decide(provider: ReasoningProvider | LegacyPlanner, context: ReasoningContext) -> Decision:
    """Use the provider boundary while keeping old plan()-based callers working."""
    decide = getattr(provider, "decide", None)
    if callable(decide):
        return decide(context)
    plan = getattr(provider, "plan", None)
    if callable(plan):
        return plan(context)
    raise TypeError("reasoning provider must implement decide() or legacy plan()")


def _action_history(
    decision: Decision,
    step: int,
    *,
    accepted: bool,
    changed: bool,
    verified: bool,
    error: str | None = None,
    task_effect: str | None = None,
    effect_evidence: str = "",
) -> dict[str, Any]:
    target = decision.action.target
    return {
        "step": step,
        "action_type": decision.action.type.value,
        "target_id": target.element_id if target else None,
        "target_text": target.text if target else "",
        "target_content_description": target.content_description if target else "",
        "accepted": accepted,
        "changed": changed,
        "verified": verified,
        "error": error,
        "task_effect": task_effect,
        "effect_evidence": effect_evidence,
    }


@dataclass
class NavigationLoop:
    bridge: NavigationBridge
    planner: ReasoningProvider | LegacyPlanner
    evaluator: GoalEvaluator = field(default_factory=GoalEvaluator)
    verifier: TransitionVerifier = field(default_factory=TransitionVerifier)
    task_effect_evaluator: TaskEffectEvaluator = field(default_factory=TaskEffectEvaluator)
    max_steps: int = 5
    settle_timeout: float = 2.0

    def run(
        self,
        goal: str,
        *,
        initial_state: WorldState | None = None,
        observe: Callable[[], WorldState] | None = None,
        refresh: Callable[[WorldState], WorldState] | None = None,
    ) -> bool:
        """Run navigation using observation callbacks supplied by the task boundary.

        The callbacks let TaskExecutor own observation acquisition/refresh while
        preserving this loop as a compatibility planner/execution engine.
        Direct callers still use the bridge when callbacks are omitted.
        """
        history: list[Mapping[str, Any]] = []
        observe_fn = observe or self.bridge.observe
        refresh_fn = refresh or (
            lambda previous: self.bridge.wait_for_fresh_observation(previous, self.settle_timeout)
        )
        state = initial_state if initial_state is not None else observe_fn()
        action_goal = self.evaluator.is_action_goal(goal)

        if not action_goal and self.evaluator.evaluate(goal, state):
            return True

        for step in range(1, self.max_steps + 1):
            context = build_reasoning_context(goal, state, history)
            decision = _decide(self.planner, context)

            is_wait = decision.action.type is ActionType.WAIT
            if is_wait:
                result = ExecutionResult(True, False)
            else:
                result = self.bridge.execute(decision.action)

            if not result.accepted:
                after = observe_fn()
                effect = self.task_effect_evaluator.evaluate(goal, decision.action, result, state, after)
                history.append(
                    _action_history(
                        decision,
                        step,
                        accepted=False,
                        changed=False,
                        verified=False,
                        error=result.error,
                        task_effect=effect.effect.value,
                        effect_evidence=effect.evidence,
                    )
                )
                state = after
                continue

            try:
                after = observe_fn() if is_wait else refresh_fn(state)
            except TimeoutError:
                result = ExecutionResult(True, False, False, "fresh observation timeout")
                effect = self.task_effect_evaluator.evaluate(goal, decision.action, result, state, None)
                history.append(
                    _action_history(
                        decision,
                        step,
                        accepted=True,
                        changed=False,
                        verified=False,
                        error=result.error,
                        task_effect=effect.effect.value,
                        effect_evidence=effect.evidence,
                    )
                )
                continue

            changed = after != state
            verified = True if is_wait else self.verifier.verify(
                state, after, ExecutionResult(True, changed, False)
            )
            effect = self.task_effect_evaluator.evaluate(
                goal,
                decision.action,
                ExecutionResult(True, changed, verified),
                state,
                after,
            )
            history.append(
                _action_history(
                    decision,
                    step,
                    accepted=True,
                    changed=changed,
                    verified=verified,
                    task_effect=effect.effect.value,
                    effect_evidence=effect.evidence,
                )
            )

            state = after
            if action_goal and verified:
                return True
            if self.evaluator.evaluate(goal, state):
                return True

        return False
