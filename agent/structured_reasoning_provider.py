from __future__ import annotations

from typing import Any, Callable, Mapping

from .core import Decision
from .reasoning_context import ReasoningContext
from .reasoning_response import decision_from_response


class StructuredReasoningProvider:
    """Adapt a structured-response callable to Nova's reasoning provider contract."""

    def __init__(self, responder: Callable[[Mapping[str, Any]], Mapping[str, Any]]):
        self._responder = responder

    def decide(self, context: ReasoningContext) -> Decision:
        """Build the provider payload, obtain a response, and validate the decision."""
        from .reasoning_payload import reasoning_payload

        response = self._responder(reasoning_payload(context))
        return decision_from_response(response, context)
