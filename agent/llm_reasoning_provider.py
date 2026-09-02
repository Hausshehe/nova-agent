from __future__ import annotations

import json
from typing import Any, Callable, Mapping

from .reasoning_context import ReasoningContext
from .reasoning_response import InvalidReasoningResponse, decision_from_response
from .reasoning_payload import reasoning_payload
from .core import Decision


_RESPONSE_CONTRACT = """Return ONLY one JSON object using exactly this decision shape:
{"action_type":"click|back|wait","target":{"element_id":"<id>"}|null,"reason":"<short explanation>"}
For click, target.element_id MUST be one of the clickable candidates in the observation.
For back or wait, target MUST be null.
Do not use an 'action' field. Do not use a top-level 'element_id' field.
"""


class LLMReasoningProvider:
    """Connect an LLM-compatible callable to Nova's structured reasoning boundary.

    The callable is responsible only for producing a structured response. Nova
    validates that response against the live observation before any action runs.
    """

    def __init__(self, responder: Callable[[str], Mapping[str, Any]]):
        self._responder = responder

    def decide(self, context: ReasoningContext) -> Decision:
        payload = reasoning_payload(context)
        prompt = _RESPONSE_CONTRACT + "\nObservation and goal:\n" + json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        try:
            response = self._responder(prompt)
        except Exception as exc:
            raise RuntimeError("reasoning provider failed") from exc
        if not isinstance(response, Mapping):
            raise InvalidReasoningResponse("LLM response must be an object")
        return decision_from_response(response, context)
