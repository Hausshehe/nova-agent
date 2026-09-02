from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .core import TransitionVerifier
from .goal_evaluator import GoalEvaluator
from .navigation import LegacyPlanner, NavigationBridge, NavigationLoop
from .reasoning_provider import ReasoningProvider


class TaskRunner(Protocol):
    """Boundary for executing one high-level task."""

    def run(self, goal: str) -> bool: ...


@dataclass
class TaskExecutor:
    """Own the high-level task boundary while migrating observation ownership.

    R2 takes the first observation at the task boundary and passes that
    snapshot into the existing verified loop. Subsequent fresh observations
    remain inside NavigationLoop until later migration stages move the rest of
    the observation/action cycle upward.
    """

    bridge: NavigationBridge
    planner: ReasoningProvider | LegacyPlanner
    evaluator: GoalEvaluator = field(default_factory=GoalEvaluator)
    verifier: TransitionVerifier = field(default_factory=TransitionVerifier)
    max_steps: int = 5
    settle_timeout: float = 2.0

    def run(self, goal: str) -> bool:
        initial_state = self.bridge.observe()
        navigation = NavigationLoop(
            bridge=self.bridge,
            planner=self.planner,
            evaluator=self.evaluator,
            verifier=self.verifier,
            max_steps=self.max_steps,
            settle_timeout=self.settle_timeout,
        )
        return navigation.run(goal, initial_state=initial_state)
