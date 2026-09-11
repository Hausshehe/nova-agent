"""Bounded, health-aware routing across independent reasoning providers."""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Mapping

Responder = Callable[[str], Mapping[str, Any]]
Sleeper = Callable[[float], None]
Clock = Callable[[], float]

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
_RETRY_AFTER_RE = re.compile(r"retry[-_ ]after\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)


@dataclass
class _ProviderState:
    cooldown_until: float = 0.0
    failures: int = 0
    successes: int = 0


class ReasoningProviderPool:
    """Route requests across providers with bounded retries and cooldowns.

    Providers are independent capacity pools. A rate-limited provider is not
    retried immediately when another provider is available. Other transient
    failures receive one bounded retry. With only one provider configured, a
    temporary 429 receives one bounded retry after the provider's advertised
    retry-after delay when available, rather than immediately repeating a
    request that is known to be rate-limited.
    """

    def __init__(
        self,
        responders: Sequence[tuple[str, Responder]],
        *,
        transient_retries: int = 1,
        retry_delay_seconds: float = 1.25,
        rate_limit_cooldown_seconds: float = 15.0,
        failure_cooldown_seconds: float = 5.0,
        sleeper: Sleeper = time.sleep,
        clock: Clock = time.monotonic,
    ) -> None:
        if not responders:
            raise ValueError("at least one reasoning responder is required")
        if transient_retries < 0:
            raise ValueError("transient_retries must not be negative")
        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must not be negative")
        if rate_limit_cooldown_seconds < 0 or failure_cooldown_seconds < 0:
            raise ValueError("cooldown values must not be negative")
        self._responders = tuple(responders)
        self._transient_retries = transient_retries
        self._retry_delay_seconds = retry_delay_seconds
        self._rate_limit_cooldown_seconds = rate_limit_cooldown_seconds
        self._failure_cooldown_seconds = failure_cooldown_seconds
        self._sleeper = sleeper
        self._clock = clock
        self._states = {name: _ProviderState() for name, _ in self._responders}
        self._cursor = 0

    @staticmethod
    def _is_transient(exc: Exception) -> bool:
        message = str(exc).lower()
        return any(marker in message for marker in _TRANSIENT_ERROR_MARKERS)

    @staticmethod
    def _is_rate_limited(exc: Exception) -> bool:
        message = str(exc).lower()
        return "http 429" in message or "rate limit" in message or "resource_exhausted" in message

    @staticmethod
    def _retry_after(exc: Exception) -> float | None:
        match = _RETRY_AFTER_RE.search(str(exc))
        if not match:
            return None
        try:
            return max(0.0, float(match.group(1)))
        except ValueError:
            return None

    def _available_indices(self) -> list[int]:
        now = self._clock()
        count = len(self._responders)
        return [
            (self._cursor + offset) % count
            for offset in range(count)
            if self._states[self._responders[(self._cursor + offset) % count][0]].cooldown_until <= now
        ]

    def __call__(self, prompt: str) -> Mapping[str, Any]:
        failures: list[str] = []
        attempted: set[int] = set()
        while len(attempted) < len(self._responders):
            available = [index for index in self._available_indices() if index not in attempted]
            if not available:
                break
            index = available[0]
            name, responder = self._responders[index]
            attempted.add(index)
            state = self._states[name]
            attempts = 0
            while True:
                try:
                    result = responder(prompt)
                    state.successes += 1
                    state.failures = 0
                    self._cursor = (index + 1) % len(self._responders)
                    return result
                except (RuntimeError, ValueError) as exc:
                    failures.append(f"{name}: {exc}")
                    state.failures += 1
                    if self._is_rate_limited(exc):
                        if len(self._responders) == 1 and attempts < self._transient_retries:
                            attempts += 1
                            delay = self._retry_after(exc)
                            self._sleeper(delay if delay is not None else self._retry_delay_seconds)
                            continue
                        retry_after = self._retry_after(exc)
                        cooldown = retry_after if retry_after is not None else self._rate_limit_cooldown_seconds
                        state.cooldown_until = self._clock() + cooldown
                        break
                    if not self._is_transient(exc) or attempts >= self._transient_retries:
                        state.cooldown_until = self._clock() + self._failure_cooldown_seconds
                        break
                    attempts += 1
                    self._sleeper(self._retry_delay_seconds)

        raise RuntimeError("all reasoning providers failed: " + "; ".join(failures))

    def health(self) -> dict[str, dict[str, float | int]]:
        now = self._clock()
        return {
            name: {
                "cooldown_seconds": max(0.0, state.cooldown_until - now),
                "failures": state.failures,
                "successes": state.successes,
            }
            for name, state in self._states.items()
        }
