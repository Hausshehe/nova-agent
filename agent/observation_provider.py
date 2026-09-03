from __future__ import annotations

import time
from typing import Protocol

from .core import WorldState


class ObservationSource(Protocol):
    """Low-level source capable of acquiring Android observations."""

    def observe(self) -> WorldState: ...


class ObservationProvider(Protocol):
    """Boundary for acquiring task observations."""

    def observe(self) -> WorldState: ...

    def refresh(self, previous: WorldState) -> WorldState: ...


class AndroidObservationProvider:
    """Own observation acquisition and Android transition settling."""

    def __init__(
        self,
        source: ObservationSource,
        settle_timeout: float = 2.0,
        poll_seconds: float = 0.2,
    ):
        self.source = source
        self.settle_timeout = settle_timeout
        self.poll_seconds = poll_seconds

    def observe(self) -> WorldState:
        return self.source.observe()

    @staticmethod
    def _same_ui(before: WorldState, after: WorldState) -> bool:
        """Compare UI state while ignoring observation identity and timestamps."""
        return (
            before.package == after.package
            and before.activity == after.activity
            and before.elements == after.elements
        )

    def refresh(self, previous: WorldState) -> WorldState:
        """Wait for a fresh observation, then return only after the UI settles."""
        deadline = time.monotonic() + self.settle_timeout
        candidate: WorldState | None = None

        while True:
            state = self.observe()

            if candidate is None:
                if state.observation_id == previous.observation_id:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            "timed out waiting for fresh Android observation "
                            f"after {previous.observation_id}"
                        )
                else:
                    candidate = state
            elif self._same_ui(candidate, state):
                return state
            else:
                candidate = state

            if time.monotonic() >= deadline:
                raise TimeoutError(
                    "timed out waiting for settled Android observation "
                    f"after {previous.observation_id}"
                )
            time.sleep(self.poll_seconds)
