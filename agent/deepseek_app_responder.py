"""Session-aware reasoning boundary for the DeepSeek Android app bridge.

This module deliberately contains no DeepSeek private protocol, network
interception, or UI automation. The Android-specific transport is injected so
Nova can keep reasoning validation independent from how the consumer app is
controlled.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


DEEPSEEK_MISSION_PROMPT = """You are Nova's Android reasoning engine.

Your job is to reason about a live Android device for Nova. Nova, not you,
controls the device. You must never claim that you executed an action.

Nova will send you the mission goal and the latest observed Android state.
For every reasoning turn, choose exactly ONE next action, based only on the
state Nova supplied. After Nova executes that action, it will send you a fresh
observation in this same conversation. Reassess the new state from scratch.

Rules:
1. Reason from the supplied live state. Never invent UI elements, ids,
   coordinates, packages, or successful outcomes.
2. Prefer semantic targets and known packages/components over coordinates.
3. Return exactly one next action. Never return an action sequence.
4. Do not treat an intended action as completed. Nova verifies completion
   from the next real Android observation.
5. Use status \"completed\" only when the supplied state proves that the goal
   is already complete.
6. Use status \"blocked\" when Nova cannot safely proceed from the evidence.
7. Use status \"uncertain\" when the evidence is insufficient to choose a
   safe action or prove completion.
8. If an attempted action failed, reason about an alternative supported by
   the new observation instead of repeating the same assumption.
9. Keep reasoning brief and practical.

Return exactly this JSON shape and no markdown:
{
  "status": "continue | completed | blocked | uncertain",
  "reasoning": "Brief explanation.",
  "action": {
    "type": "tap | input_text | back | launch_app | wait | none",
    "target": "Semantic target, package/component, or null",
    "text": "Text to enter when required, otherwise null"
  },
  "expected_outcome": "What Nova should verify after the action.",
  "confidence": 0.0
}

Important: \"completed\" is never a valid response merely because there is
nothing to do in the prompt. Completion requires evidence that the requested
mission goal has actually been achieved on Android."""


class DeepSeekAppTransport(Protocol):
    """Android-facing transport for one DeepSeek mission conversation."""

    def start_new_chat(self) -> str:
        """Create/open one fresh DeepSeek conversation and return its handle."""
        ...

    def send_prompt(self, session_id: str, prompt: str) -> Mapping[str, Any]:
        """Send a prompt through the active DeepSeek app conversation."""
        ...


class DeepSeekAppResponder:
    """Expose one DeepSeek app conversation as a reasoning callable.

    One responder instance owns one mission conversation. ``begin_mission``
    starts a fresh chat and sends the role/setup prompt before any mission
    reasoning turn. The setup response is intentionally ignored. The same chat
    is then reused for every reasoning turn in that mission.
    """

    def __init__(self, transport: DeepSeekAppTransport) -> None:
        self._transport = transport
        self._session_id: str | None = None

    @property
    def session_id(self) -> str | None:
        """Return the current DeepSeek conversation handle, if one exists."""
        return self._session_id

    def begin_mission(self) -> str:
        """Start a fresh chat and establish DeepSeek's Nova reasoning role."""
        session_id = self._transport.start_new_chat()
        if not isinstance(session_id, str) or not session_id.strip():
            raise RuntimeError("DeepSeek app returned an invalid mission session")
        self._session_id = session_id
        self._transport.send_prompt(session_id, DEEPSEEK_MISSION_PROMPT)
        return session_id

    def __call__(self, prompt: str) -> Mapping[str, Any]:
        """Send one reasoning turn through the existing mission conversation."""
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("DeepSeek prompt must not be blank")
        if self._session_id is None:
            raise RuntimeError("DeepSeek mission session has not been started")
        response = self._transport.send_prompt(self._session_id, prompt)
        if not isinstance(response, Mapping):
            raise RuntimeError("DeepSeek app returned a non-object reasoning response")
        return response
