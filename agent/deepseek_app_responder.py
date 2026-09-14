"""Session-aware reasoning boundary for the DeepSeek Android app bridge.

This module deliberately contains no DeepSeek private protocol, network
interception, or UI automation. The Android-specific transport is injected so
Nova can keep reasoning validation independent from how the consumer app is
controlled.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


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

    One responder instance owns one mission conversation. Call ``begin_mission``
    exactly once before reasoning, then reuse the responder for every reasoning
    turn in that mission. A new mission must use a fresh responder instance or
    call ``begin_mission`` explicitly to replace the session.
    """

    def __init__(self, transport: DeepSeekAppTransport) -> None:
        self._transport = transport
        self._session_id: str | None = None

    @property
    def session_id(self) -> str | None:
        """Return the current DeepSeek conversation handle, if one exists."""
        return self._session_id

    def begin_mission(self) -> str:
        """Start a fresh DeepSeek chat for the next Nova mission."""
        session_id = self._transport.start_new_chat()
        if not isinstance(session_id, str) or not session_id.strip():
            raise RuntimeError("DeepSeek app returned an invalid mission session")
        self._session_id = session_id
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
