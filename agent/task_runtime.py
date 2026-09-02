from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from .core import ActionType, ExecutionResult, TransitionVerifier, WorldState
from .goal_evaluator import GoalEvaluator
from .navigation import LegacyPlanner, NavigationBridge, _action_history, _decide
from .reasoning_context import build_reasoning_context
from .reasoning_provider import ReasoningProvider


class TaskRunner(Protocol):
    """Boundary for executing one high-level task."""

    def run(self, goal: str) -> bool: ...


@dataclass
class TaskExecutor:
    """Own the complete lifecycle of one high-level task.

    The runtime owns task state, history, step progression, observation
    acquisition, action execution, transition verification, and termination.
    NavigationLoop remains available as a compatibility component for legacy
    callers, but new task execution no longer delegates its lifecycle to it.
    """

    bridge: NavigationBridge
    planner: ReasoningProvider | LegacyPlanner
    evaluator: GoalEvaluator = field(default_factory=GoalEvaluator)
    verifier: TransitionVerifier = field(default_factory=TransitionVerifier)
    max_steps: int = 5
    settle_timeout: float = 2.0
    current_state: WorldState | None = field(default=None, init=False)
    history: list[Mapping[str, Any]] = field(default_factory=list, init=False)
    current_step: int = field(default=0, init=False)

    def _observe(self) -> WorldState:
        self.current_state = self.bridge.observe()
        return self.current_state

    def _refresh(self, previous: WorldState) -> WorldState:
        self.current_state = self.bridge.wait_for_fresh_observation(
            previous,
            self.settle_timeout,
        )
        return self.current_state

    def run(self, goal: str) -> bool:
        """Execute one task until verified completion or the step budget ends."""
        self.history.clear()
        self.current_step = 0
        state = self._observe()
        action_goal = self.evaluator.is_action_goal(goal)

        if not action_goal and self.evaluator.evaluate(goal, state):
            return True

        for step in range(1, self.max_steps + 1):
            self.current_step = step
            context = build_reasoning_context(goal, state, self.history)
            decision = _decide(self.planner, context)

            is_wait = decision.action.type is ActionType.WAIT
            if is_wait:
                result = ExecutionResult(True, False)
            else:
                result = self.bridge.execute(decision.action)

            if not result.accepted:
                self.history.append(
                    _action_history(
                        decision,
                        step,
                        accepted=False,
                        changed=False,
                        verified=False,
                        error=result.error,
                    )
                )
                state = self._observe()
                continue

            try:
                after = self._observe() if is_wait else self._refresh(state)
            except TimeoutError:
                self.history.append(
                    _action_history(
                        decision,
                        step,
                        accepted=True,
                        changed=False,
                        verified=False,
                        error="fresh observation timeout",
                    )
                )
                continue

            changed = after != state
            verified = True if is_wait else self.verifier.verify(
                state, after, ExecutionResult(True, changed, False)
            )
            self.history.append(
                _action_history(
                    decision,
                    step,
                    accepted=True,
                    changed=changed,
                    verified=verified,
                )
            )

            state = after
            if action_goal and verified:
                return True
            if self.evaluator.evaluate(goal, state):
                return True

        return False
