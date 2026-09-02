from __future__ import annotations

from typing import Protocol

from .core import Decision
from .reasoning_context import ReasoningContext


class ReasoningProvider(Protocol):
    """Provider-neutral interface for choosing Nova's next action."""

    def decide(self, context: ReasoningContext) -> Decision:
        """Return the next action decision for the current reasoning context."""
        ...
