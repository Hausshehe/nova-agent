from __future__ import annotations

import json
from typing import Any, Callable, Mapping

from .reasoning_context import ReasoningContext
from .reasoning_response import InvalidReasoningResponse, decision_from_response
from .reasoning_payload import reasoning_payload
from .core import Decision


class LLMReasoningProvider:
    """Connect an LLM-compatible callable to Nova's structured reasoning boundary.

    The callable is responsible only for producing a structured response. Nova
    validates that response against the live observation before any action runs.
    """

    def __init__(self, responder: Callable[[str], Mapping[str, Any]]):
        self._responder = responder

    def decide(self, context: ReasoningContext) -> Decision:
        payload = reasoning_payload(context)
        prompt = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        try:
            response = self._responder(prompt)
        except Exception as exc:
            raise RuntimeError("reasoning provider failed") from exc
        if not isinstance(response, Mapping):
            raise InvalidReasoningResponse("LLM response must be an object")
        return decision_from_response(response, context)
