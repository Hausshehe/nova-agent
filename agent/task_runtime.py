from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .goal_evaluator import GoalEvaluator
from .navigation import LegacyPlanner, NavigationBridge, NavigationLoop
from .core import TransitionVerifier
from .reasoning_provider import ReasoningProvider


class TaskRunner(Protocol):
    """Boundary for executing one high-level task."""

    def run(self, goal: str) -> bool: ...


@dataclass
class TaskExecutor:
    """Own the high-level task boundary while preserving the verified loop.

    R1 intentionally delegates execution to the existing NavigationLoop. This
    establishes the new task-oriented entry point without changing Android
    behavior. Later migration stages can move observation, action, verification,
    and recovery responsibilities behind this boundary one at a time.
    """

    bridge: NavigationBridge
    planner: ReasoningProvider | LegacyPlanner
    evaluator: GoalEvaluator = field(default_factory=GoalEvaluator)
    verifier: TransitionVerifier = field(default_factory=TransitionVerifier)
    max_steps: int = 5
    settle_timeout: float = 2.0

    def run(self, goal: str) -> bool:
        navigation = NavigationLoop(
            bridge=self.bridge,
            planner=self.planner,
            evaluator=self.evaluator,
            verifier=self.verifier,
            max_steps=self.max_steps,
            settle_timeout=self.settle_timeout,
        )
        return navigation.run(goal)
