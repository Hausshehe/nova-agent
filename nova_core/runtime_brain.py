"""Mission-level runtime brain for Nova Agent v2.

The brain owns the lifecycle of one Android task. It coordinates observation,
reasoning, execution, and verification without knowing how Android or an LLM
provider performs those operations. This keeps the continuous feedback loop
explicit while preserving the existing RunController as the state authority.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Decision, ExecutionResult, Goal, Observation, RunResult, RunStatus
from .reasoning import ReasoningContext
from .run_controller import RunController
from .state_machine import RunState


@dataclass
class RuntimeBrain:
    """Own the mission-level feedback loop for a single bounded run."""

    controller: RunController
    goal_verified: bool = False

    @classmethod
    def create(cls, goal: Goal, max_steps: int = 20) -> "RuntimeBrain":
        """Create a fresh mission without starting Android work."""
        return cls(RunController(goal=goal, max_steps=max_steps))

    @property
    def state(self) -> RunState:
        return self.controller.state

    @property
    def goal(self) -> Goal:
        return self.controller.goal

    def start(self) -> None:
        """Start the mission and request the first observation."""
        self.controller.move(RunState.OBSERVING)

    def record_observation(self, observation: Observation) -> None:
        """Record the current UI and move to reasoning."""
        self.controller.record_observation(observation)
        self.controller.move(RunState.DECIDING)

    def reasoning_context(self) -> ReasoningContext:
        """Build the provider-neutral context for the next decision."""
        observation = self.controller.observation
        if self.state != RunState.DECIDING or observation is None:
            raise RuntimeError("reasoning context requires a current observation")
        return ReasoningContext(
            goal=self.goal,
            observation=observation,
            history=self.controller.history,
        )

    def record_decision(self, decision: Decision) -> None:
        """Record the chosen action and move to execution."""
        self.controller.record_decision(decision)
        self.controller.move(RunState.EXECUTING)

    def record_execution(self, result: ExecutionResult) -> None:
        """Record the native execution result and move to verification."""
        self.controller.record_execution(result)
        self.controller.move(RunState.VERIFYING)

    def record_post_observation(self, observation: Observation) -> None:
        """Record the fresh UI after an action and return to observation."""
        self.controller.record_post_observation(observation)
        self.controller.move(RunState.OBSERVING)

    def complete(self) -> RunResult:
        """Mark the mission successful only after the caller verified its goal."""
        self.goal_verified = True
        return self.controller.finish(RunStatus.SUCCEEDED)

    def fail(self, error: str) -> RunResult:
        """Terminate the mission as failed without claiming goal completion."""
        self.goal_verified = False
        return self.controller.finish(RunStatus.FAILED, error=error)

    def abort(self, error: str | None = None) -> RunResult:
        """Terminate the mission as aborted without claiming completion."""
        self.goal_verified = False
        return self.controller.finish(RunStatus.ABORTED, error=error)
