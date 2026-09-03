from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from .action_executor import ActionExecutor
from .action_guard import ActionGuard
from .core import Decision, ExecutionResult, TransitionVerifier, WorldState
from .goal_evaluator import GoalEvaluator
from .navigation import LegacyPlanner, NavigationBridge, _action_history, _decide
from .observation_provider import AndroidObservationProvider, ObservationProvider
from .reasoning_context import build_reasoning_context
from .reasoning_provider import ReasoningProvider
from .recovery_engine import RecoveryEngine
from .task_effect import TaskEffect, TaskEffectEvaluator
from .task_state import TaskState


class TaskRunner(Protocol):
    """Boundary for executing one high-level task."""

    def run(self, goal: str) -> bool: ...


@dataclass
class TaskExecutor:
    """Own the complete lifecycle of one high-level task."""

    bridge: NavigationBridge
    planner: ReasoningProvider | LegacyPlanner
    evaluator: GoalEvaluator = field(default_factory=GoalEvaluator)
    verifier: TransitionVerifier = field(default_factory=TransitionVerifier)
    task_effect_evaluator: TaskEffectEvaluator = field(default_factory=TaskEffectEvaluator)
    task_state: TaskState = field(default_factory=TaskState, init=False)
    max_steps: int = 5
    settle_timeout: float = 2.0
    observation_provider: ObservationProvider | None = None
    recovery_engine: RecoveryEngine = field(default_factory=RecoveryEngine)
    action_guard: ActionGuard = field(default_factory=ActionGuard)
    current_state: WorldState | None = field(default=None, init=False)
    history: list[Mapping[str, Any]] = field(default_factory=list, init=False)
    current_step: int = field(default=0, init=False)
    action_executor: ActionExecutor = field(init=False)
    _goal: str = field(default="", init=False)

    def __post_init__(self) -> None:
        if self.observation_provider is None:
            self.observation_provider = AndroidObservationProvider(
                self.bridge,
                settle_timeout=self.settle_timeout,
            )
        self.action_executor = ActionExecutor(
            bridge=self.bridge,
            verifier=self.verifier,
            observation_provider=self.observation_provider,
            settle_timeout=self.settle_timeout,
        )

    def _observe(self) -> WorldState:
        self.current_state = self.observation_provider.observe()
        return self.current_state

    def _record_effect(
        self,
        decision: Decision,
        step: int,
        *,
        accepted: bool,
        changed: bool,
        verified: bool,
        error: str | None,
        state_before: WorldState,
        state_after: WorldState | None,
    ) -> TaskEffect:
        effect = self.task_effect_evaluator.evaluate(
            self._goal,
            decision.action,
            ExecutionResult(accepted, changed, verified, error),
            state_before,
            state_after,
        )
        self.task_state.apply(decision.action, effect, state_before, state_after)
        self.history.append(
            _action_history(
                decision,
                step,
                accepted=accepted,
                changed=changed,
                verified=verified,
                error=error,
                task_effect=effect.effect.value,
                effect_evidence=effect.evidence,
            )
        )
        return effect.effect

    def _guard_decision(self, decision: Decision, state: WorldState, step: int) -> bool:
        """Reject constrained proposals before they can reach Android."""
        result = self.action_guard.check(decision.action, state, self.task_state)
        if result.allowed:
            return True

        error = f"action guard blocked: {result.reason}"
        if result.evidence:
            error = f"{error}: {result.evidence}"
        self.history.append(
            _action_history(
                decision,
                step,
                accepted=False,
                changed=False,
                verified=False,
                error=error,
                task_effect=TaskEffect.BLOCKED.value,
                effect_evidence=result.evidence,
            )
        )
        return False

    def _recover(self, goal: str, state: WorldState) -> Decision:
        return self.recovery_engine.recover(
            goal,
            state,
            self.history,
            self.planner,
            self.task_state,
        )

    def run(self, goal: str) -> bool:
        """Execute one task until verified completion or the step budget ends."""
        self.history.clear()
        self.current_step = 0
        self.recovery_engine.reset()
        self.task_state.reset()
        self._goal = goal
        state = self._observe()
        self.current_state = state
        action_goal = self.evaluator.is_action_goal(goal)
        next_decision: Decision | None = None

        if not action_goal and self.evaluator.evaluate(goal, state):
            return True

        for step in range(1, self.max_steps + 1):
            self.current_step = step
            if next_decision is None:
                context = build_reasoning_context(goal, state, self.history, self.task_state)
                decision = _decide(self.planner, context)
            else:
                decision = next_decision
                next_decision = None

            if not self._guard_decision(decision, state, step):
                if step < self.max_steps:
                    next_decision = self._recover(goal, state)
                continue

            result, after, verified = self.action_executor.execute(decision.action, state)

            if not result.accepted:
                state_after = after if after is not None else self._observe()
                self._record_effect(
                    decision,
                    step,
                    accepted=False,
                    changed=False,
                    verified=False,
                    error=result.error,
                    state_before=state,
                    state_after=state_after,
                )
                state = state_after
                self.current_state = state
                if step < self.max_steps:
                    next_decision = self._recover(goal, state)
                continue

            if after is None:
                self._record_effect(
                    decision,
                    step,
                    accepted=True,
                    changed=False,
                    verified=False,
                    error=result.error or "fresh observation timeout",
                    state_before=state,
                    state_after=None,
                )
                if step < self.max_steps:
                    next_decision = self._recover(goal, state)
                continue

            changed = result.changed
            effect = self._record_effect(
                decision,
                step,
                accepted=True,
                changed=changed,
                verified=verified,
                error=result.error,
                state_before=state,
                state_after=after,
            )

            state = after
            self.current_state = state
            if action_goal and effect is TaskEffect.COMPLETED:
                return True
            if not action_goal and self.evaluator.evaluate(goal, state):
                return True
            if effect in {TaskEffect.BLOCKED, TaskEffect.FAILED, TaskEffect.UNKNOWN} and step < self.max_steps:
                next_decision = self._recover(goal, state)

        return False
