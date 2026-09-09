"""Mission-level runtime brain for Nova Agent v2.

The brain owns the mission lifecycle for one bounded run. It coordinates
observation, reasoning, execution, verification, and a bounded working-memory
window without knowing how Android or an LLM provider performs those operations.
The existing RunController remains the authoritative state owner.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Decision, ExecutionResult, Goal, Observation, RunResult, RunStatus
from .reasoning import ReasoningContext
from .run_controller import RunController
from .state_machine import RunState
from .working_memory import WorkingMemory


@dataclass
class RuntimeBrain:
    """Own the mission-level lifecycle for a single bounded run."""

    controller: RunController
    goal_verified: bool = False
    memory: WorkingMemory = field(init=False)

    def __post_init__(self) -> None:
        self.memory = WorkingMemory(goal=self.controller.goal)

    @classmethod
    def create(
        cls, goal: Goal, max_steps: int = 20, max_memory_history: int = 6
    ) -> "RuntimeBrain":
        """Create a fresh mission without starting Android work."""
        brain = cls(RunController(goal=goal, max_steps=max_steps))
        brain.memory = WorkingMemory(goal=goal, max_history=max_memory_history)
        return brain

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
        self.memory.observe(observation)
        self.controller.move(RunState.DECIDING)

    def reasoning_context(self, *, evidence: object | None = None) -> ReasoningContext:
        """Build provider-neutral context from bounded working memory."""
        observation = self.memory.observation
        if self.state != RunState.DECIDING or observation is None:
            raise RuntimeError("reasoning context requires a current observation")
        return ReasoningContext(
            goal=self.goal,
            observation=observation,
            history=self.memory.history,
            evidence=evidence,
        )

    def record_decision(self, decision: Decision) -> None:
        """Record the chosen action and move to execution."""
        self.controller.record_decision(decision)
        self.controller.move(RunState.EXECUTING)

    def record_execution(self, result: ExecutionResult) -> None:
        """Record execution, then add its reasoning step to working memory."""
        self.controller.record_execution(result)
        self.memory.remember_step(self.controller.history[-1])
        self.controller.move(RunState.VERIFYING)

    def finish_verification(
        self, observation: Observation, *, goal_achieved: bool
    ) -> RunResult | None:
        """Record fresh UI and finish or return to the observation loop."""
        self.controller.record_post_observation(observation)
        self.memory.remember_post_observation(observation)
        if goal_achieved:
            self.goal_verified = True
            return self.controller.finish(RunStatus.SUCCEEDED)
        self.controller.move(RunState.OBSERVING)
        return None

    def verify_post_observation(
        self, observation: Observation, *, goal_achieved: bool
    ) -> RunResult | None:
        """Compatibility alias for the explicit verification lifecycle method."""
        return self.finish_verification(observation, goal_achieved=goal_achieved)

    def record_post_observation(self, observation: Observation) -> None:
        """Record fresh UI when verification says the mission is not complete."""
        self.finish_verification(observation, goal_achieved=False)

    def complete(self) -> RunResult:
        """Mark success only after a fresh post-action observation was recorded."""
        if self.state is not RunState.VERIFYING:
            raise RuntimeError("goal completion must be verified from the verifying state")
        if not self.controller.history or self.controller.history[-1].post_observation is None:
            raise RuntimeError("goal completion requires a verified post-observation")
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
