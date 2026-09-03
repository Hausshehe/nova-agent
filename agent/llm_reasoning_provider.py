from __future__ import annotations

import json
from typing import Any, Callable, Mapping

from .core import Decision
from .reasoning_context import ReasoningContext
from .reasoning_payload import reasoning_payload
from .reasoning_response import InvalidReasoningResponse, decision_from_response


_RESPONSE_CONTRACT = """Return ONLY one JSON object:
{"action_type":"click|back|wait","target":{"element_id":"<id>"}|null,"reason":"<short explanation>"}
Use only an actionable candidate from the CURRENT observation. The current observation is authoritative.
The goal describes the desired outcome, not an instruction to click a similarly named element immediately.
Use history to understand what has already happened. After every executed action, reason again from the fresh observation.
Never assume an accepted Android action completed the task. Never repeat an action just because it was previously chosen.
"""


class LLMReasoningProvider:
    def __init__(self, responder: Callable[[str], Mapping[str, Any]]):
        self._responder = responder

    def decide(self, context: ReasoningContext) -> Decision:
        prompt = _RESPONSE_CONTRACT + "\nObservation and goal:\n" + json.dumps(
            reasoning_payload(context), ensure_ascii=False, separators=(",", ":")
        )
        try:
            response = self._responder(prompt)
        except Exception as exc:
            raise RuntimeError(f"reasoning provider failed: {type(exc).__name__}: {exc}") from exc
        if not isinstance(response, Mapping):
            raise InvalidReasoningResponse("LLM response must be an object")
        return decision_from_response(response, context)
