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

Reason from the CURRENT OBSERVATION, not from the goal text alone.
The goal describes the desired end state. It does NOT mean that a UI element
whose label resembles the goal should be clicked immediately.
Treat visible UI text, status messages, and the current observation as the
authoritative description of what has actually happened.
Use the action history to understand what has already been attempted.
Never claim that the goal is complete unless the current observation provides
evidence that it is complete.
If an action appears to require a prerequisite that has not been established,
do not choose that action yet. Prefer an available action that advances the
current state toward the goal.
After a failed or rejected attempt, re-evaluate the fresh observation before
choosing the next action. Do not assume that an accepted Android click means
the intended task was completed.
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
            raise RuntimeError(f"reasoning provider failed: {type(exc).__name__}: {exc}") from exc
        if not isinstance(response, Mapping):
            raise InvalidReasoningResponse("LLM response must be an object")
        return decision_from_response(response, context)
