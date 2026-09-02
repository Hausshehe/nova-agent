from __future__ import annotations

from typing import Protocol

from .core import WorldState


class ObservationSource(Protocol):
    """Low-level source capable of acquiring Android observations."""

    def observe(self) -> WorldState: ...

    def wait_for_fresh_observation(
        self,
        previous: WorldState,
        timeout: float,
    ) -> WorldState: ...


class ObservationProvider(Protocol):
    """Boundary for acquiring task observations."""

    def observe(self) -> WorldState: ...

    def refresh(self, previous: WorldState) -> WorldState: ...


class AndroidObservationProvider:
    """Own observation acquisition and Android transition settling."""

    def __init__(self, source: ObservationSource, settle_timeout: float = 2.0):
        self.source = source
        self.settle_timeout = settle_timeout

    def observe(self) -> WorldState:
        return self.source.observe()

    def refresh(self, previous: WorldState) -> WorldState:
        return self.source.wait_for_fresh_observation(previous, self.settle_timeout)
