"""Bounded working memory for one Nova Agent mission.

Working memory is a context boundary, not a second runtime state machine. The
RunController remains the authoritative owner of lifecycle state and complete
history; this object keeps only the recent evidence needed for the next
reasoning decision.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .models import Goal, Observation
from .reasoning import ReasoningStep


@dataclass
class WorkingMemory:
    """Keep the current observation and a bounded recent reasoning window."""

    goal: Goal
    max_history: int = 6
    observation: Observation | None = None
    history: tuple[ReasoningStep, ...] = ()

    def __post_init__(self) -> None:
        if self.max_history < 1:
            raise ValueError("max_history must be at least 1")

    def observe(self, observation: Observation) -> None:
        """Make an observation the current working-memory state."""
        self.observation = observation

    def remember_step(self, step: ReasoningStep) -> None:
        """Remember a completed action while enforcing the memory bound."""
        self.history = (self.history + (step,))[-self.max_history :]

    def remember_post_observation(self, observation: Observation) -> None:
        """Attach fresh verification evidence to the latest remembered step."""
        self.observation = observation
        if not self.history:
            return
        self.history = self.history[:-1] + (
            replace(self.history[-1], post_observation=observation),
        )
