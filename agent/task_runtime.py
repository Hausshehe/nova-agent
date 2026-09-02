from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from .action_executor import ActionExecutor
from .core import TransitionVerifier, WorldState
from .goal_evaluator import GoalEvaluator
from .navigation import LegacyPlanner, NavigationBridge, _action_history, _decide
from .reasoning_context import build_reasoning_context
from .reasoning_provider import ReasoningProvider


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
    max_steps: int = 5
    settle_timeout: float = 2.0
    current_state: WorldState | None = field(default=None, init=False)
    history: list[Mapping[str, Any]] = field(default_factory=list, init=False)
    current_step: int = field(default=0, init=False)
    action_executor: ActionExecutor = field(init=False)

    def __post_init__(self) -> None:
        self.action_executor = ActionExecutor(
            bridge=self.bridge,
            verifier=self.verifier,
            settle_timeout=self.settle_timeout,
        )

    def _observe(self) -> WorldState:
        self.current_state = self.bridge.observe()
        return self.current_state

    def run(self, goal: str) -> bool:
        """Execute one task until verified completion or the step budget ends."""
        self.history.clear()
        self.current_step = 0
        state = self._observe()
        self.current_state = state
        action_goal = self.evaluator.is_action_goal(goal)

        if not action_goal and self.evaluator.evaluate(goal, state):
            return True

        for step in range(1, self.max_steps + 1):
            self.current_step = step
            context = build_reasoning_context(goal, state, self.history)
            decision = _decide(self.planner, context)
            result, after, verified = self.action_executor.execute(decision.action, state)

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
                state = after if after is not None else self._observe()
                self.current_state = state
                continue

            if after is None:
                self.history.append(
                    _action_history(
                        decision,
                        step,
                        accepted=True,
                        changed=False,
                        verified=False,
                        error=result.error or "fresh observation timeout",
                    )
                )
                continue

            changed = result.changed
            self.history.append(
                _action_history(
                    decision,
                    step,
                    accepted=True,
                    changed=changed,
                    verified=verified,
                    error=result.error,
                )
            )

            state = after
            self.current_state = state
            if action_goal and verified:
                return True
            if self.evaluator.evaluate(goal, state):
                return True

        return False
