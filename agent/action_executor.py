from __future__ import annotations

from dataclasses import dataclass

from .core import Action, ActionType, ExecutionResult, TransitionVerifier, WorldState
from .navigation import NavigationBridge
from .observation_provider import ObservationProvider


@dataclass
class ActionExecutor:
    """Execute one validated action at the Android capability boundary."""

    bridge: NavigationBridge
    verifier: TransitionVerifier
    observation_provider: ObservationProvider | None = None
    settle_timeout: float = 2.0

    def __post_init__(self) -> None:
        if self.observation_provider is None:
            from .observation_provider import AndroidObservationProvider

            self.observation_provider = AndroidObservationProvider(
                self.bridge,
                settle_timeout=self.settle_timeout,
            )

    def execute(self, action: Action, previous: WorldState) -> tuple[ExecutionResult, WorldState | None, bool]:
        """Execute an action and return its result, resulting state, and verification."""
        is_wait = action.type is ActionType.WAIT
        if is_wait:
            result = ExecutionResult(True, False)
        else:
            result = self.bridge.execute(action)

        if not result.accepted:
            try:
                after = self.observation_provider.refresh(previous)
            except TimeoutError:
                after = self.observation_provider.observe()
            return result, after, False

        try:
            after = (
                self.observation_provider.observe()
                if is_wait
                else self.observation_provider.refresh(previous)
            )
        except TimeoutError as exc:
            # A settling timeout must not force the runtime to reason from the
            # stale pre-action state. Capture the newest available observation
            # and make verification/effect classification explicitly unknown.
            try:
                after = self.observation_provider.observe()
            except Exception:
                after = None
            return ExecutionResult(
                accepted=True,
                changed=False,
                verified=False,
                error=f"fresh observation timeout: {exc}",
            ), after, False

        changed = not self._same_ui(previous, after)
        verified = True if is_wait else self.verifier.verify(
            previous,
            after,
            ExecutionResult(True, changed, False),
        )
        return ExecutionResult(True, changed, verified), after, verified

    @staticmethod
    def _same_ui(before: WorldState, after: WorldState) -> bool:
        return (
            before.package == after.package
            and before.activity == after.activity
            and before.elements == after.elements
        )
