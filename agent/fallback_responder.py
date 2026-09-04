"""Bounded failover across independent reasoning providers."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Mapping


Responder = Callable[[str], Mapping[str, Any]]


class FallbackResponder:
    """Try configured responders in order, once each, for one reasoning call."""

    def __init__(self, responders: Sequence[tuple[str, Responder]]) -> None:
        if not responders:
            raise ValueError("at least one reasoning responder is required")
        self._responders = tuple(responders)

    def __call__(self, prompt: str) -> Mapping[str, Any]:
        failures: list[str] = []
        for name, responder in self._responders:
            try:
                return responder(prompt)
            except (RuntimeError, ValueError) as exc:
                failures.append(f"{name}: {exc}")

        raise RuntimeError("all reasoning providers failed: " + "; ".join(failures))
