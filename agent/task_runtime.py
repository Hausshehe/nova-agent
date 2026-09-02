from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .core import TransitionVerifier, WorldState
from .goal_evaluator import GoalEvaluator
from .navigation import LegacyPlanner, NavigationBridge, NavigationLoop
from .reasoning_provider import ReasoningProvider


class TaskRunner(Protocol):
    """Boundary for executing one high-level task."""

    def run(self, goal: str) -> bool: ...


@dataclass
class TaskExecutor:
    """Own the high-level task boundary and observation lifecycle.

    R2 moves both initial and ongoing observation acquisition to this boundary.
    NavigationLoop remains a compatibility engine for reasoning/action execution
    and no longer needs to know how the task runtime obtains fresh state.
    """

    bridge: NavigationBridge
    planner: ReasoningProvider | LegacyPlanner
    evaluator: GoalEvaluator = field(default_factory=GoalEvaluator)
    verifier: TransitionVerifier = field(default_factory=TransitionVerifier)
    max_steps: int = 5
    settle_timeout: float = 2.0
    current_state: WorldState | None = field(default=None, init=False)

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
        initial_state = self._observe()
        navigation = NavigationLoop(
            bridge=self.bridge,
            planner=self.planner,
            evaluator=self.evaluator,
            verifier=self.verifier,
            max_steps=self.max_steps,
            settle_timeout=self.settle_timeout,
        )
        return navigation.run(
            goal,
            initial_state=initial_state,
            observe=self._observe,
            refresh=self._refresh,
        )
