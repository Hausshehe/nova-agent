"""Bounded failover across independent reasoning providers."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import Any, Mapping


Responder = Callable[[str], Mapping[str, Any]]
Sleeper = Callable[[float], None]

_TRANSIENT_ERROR_MARKERS = (
    "http 408",
    "http 429",
    "http 500",
    "http 502",
    "http 503",
    "http 504",
    "temporarily overloaded",
    "timed out",
    "timeout",
    "connection",
    "connection aborted",
    "software caused connection abort",
)


class FallbackResponder:
    """Fail over across providers with one bounded retry for transient errors."""

    def __init__(
        self,
        responders: Sequence[tuple[str, Responder]],
        *,
        transient_retries: int = 1,
        retry_delay_seconds: float = 1.25,
        sleeper: Sleeper = time.sleep,
    ) -> None:
        if not responders:
            raise ValueError("at least one reasoning responder is required")
        if transient_retries < 0:
            raise ValueError("transient_retries must not be negative")
        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must not be negative")
        self._responders = tuple(responders)
        self._transient_retries = transient_retries
        self._retry_delay_seconds = retry_delay_seconds
        self._sleeper = sleeper

    @staticmethod
    def _is_transient(exc: Exception) -> bool:
        message = str(exc).lower()
        return any(marker in message for marker in _TRANSIENT_ERROR_MARKERS)

    def __call__(self, prompt: str) -> Mapping[str, Any]:
        failures: list[str] = []
        for name, responder in self._responders:
            attempts = 0
            while True:
                try:
                    return responder(prompt)
                except (RuntimeError, ValueError) as exc:
                    failures.append(f"{name}: {exc}")
                    if not self._is_transient(exc) or attempts >= self._transient_retries:
                        break
                    attempts += 1
                    self._sleeper(self._retry_delay_seconds)

        raise RuntimeError("all reasoning providers failed: " + "; ".join(failures))
