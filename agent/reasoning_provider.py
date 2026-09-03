from __future__ import annotations

from typing import Protocol

from .core import Decision
from .reasoning_context import ReasoningContext


class ReasoningProvider(Protocol):
    def decide(self, context: ReasoningContext) -> Decision: ...
