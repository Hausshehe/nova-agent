"""Small orchestration boundary for Nova Agent v2.

The controller owns run-state progression, the successful-action step budget,
and the completed reasoning history, but it does not observe Android, call a
reasoning provider, or execute actions.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .models import Goal, Observation, Decision, ExecutionResult, RunResult, RunStatus
from .reasoning import ReasoningStep
from .state_machine import InvalidTransition, RunState, is_terminal, transition


@dataclass
class RunController:
    """Own one bounded run without performing runtime work."""

    goal: Goal
    max_steps: int = 20
    state: RunState = RunState.CREATED
    steps: int = 0
    observation: Observation | None = None
    decision: Decision | None = None
    last_execution: ExecutionResult | None = None
    history: tuple[ReasoningStep, ...] = ()
    error: str | None = None

    def __post_init__(self) -> None:
        if self.max_steps < 1:
            raise ValueError("max_steps must be at least 1")

    def move(self, target: RunState) -> RunState:
        """Perform exactly one validated state transition."""
        self.state = transition(self.state, target)
        return self.state

    def record_observation(self, observation: Observation) -> None:
        """Attach an observation; state progression remains explicit."""
        if self.state != RunState.OBSERVING:
            raise InvalidTransition("observation can only be recorded while observing")
        self.observation = observation

    def record_decision(self, decision: Decision) -> None:
        """Attach a decision; no execution occurs here."""
        if self.state != RunState.DECIDING:
            raise InvalidTransition("decision can only be recorded while deciding")
        self.decision = decision

    def record_execution(self, result: ExecutionResult) -> None:
        """Attach an execution result and consume budget only for real progress."""
        if self.state != RunState.EXECUTING:
            raise InvalidTransition("execution can only be recorded while executing")
        if self.decision is None:
            raise RuntimeError("execution cannot be recorded without a decision")
        if self.steps >= self.max_steps and result.accepted and result.changed:
            raise RuntimeError("step budget exhausted")
        self.last_execution = result
        if result.accepted and result.changed:
            self.steps += 1
        self.history = self.history + (ReasoningStep(self.decision, result),)

    def record_post_observation(self, observation: Observation) -> None:
        """Attach the fresh result of the current action to its history entry."""
        if self.state != RunState.VERIFYING:
            raise InvalidTransition("post-observation can only be recorded while verifying")
        if not self.history:
            raise RuntimeError("post-observation cannot be recorded without execution history")
        self.history = self.history[:-1] + (
            replace(self.history[-1], post_observation=observation),
        )

    def finish(self, status: RunStatus, error: str | None = None) -> RunResult:
        """Enter one terminal state explicitly and return the run result."""
        targets = {
            RunStatus.SUCCEEDED: RunState.SUCCEEDED,
            RunStatus.FAILED: RunState.FAILED,
            RunStatus.ABORTED: RunState.ABORTED,
        }
        if status not in targets:
            raise ValueError("finish requires a terminal RunStatus")
        self.error = error
        self.move(targets[status])
        return RunResult(status=status, steps=self.steps, error=error)

    def result(self) -> RunResult | None:
        """Return a result only after the controller reaches a terminal state."""
        if not is_terminal(self.state):
            return None
        status = RunStatus(self.state.value)
        return RunResult(status=status, steps=self.steps, error=self.error)
