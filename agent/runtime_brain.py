from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .core import Decision
from .goal_evaluator import GoalEvaluator
from .navigation import LegacyPlanner, NavigationBridge, NavigationLoop
from .reasoning_context import ReasoningContext
from .reasoning_provider import ReasoningProvider


@dataclass(frozen=True)
class RuntimeBrainConfig:
    """Safety limits for one autonomous task episode."""

    max_steps: int = 5
    settle_timeout: float = 2.0
    provider_attempts: int = 2


@dataclass(frozen=True)
class RuntimeEvent:
    """Small, structured record of a runtime decision boundary."""

    phase: str
    detail: str = ""
    step: int | None = None
    data: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeBrainResult:
    """Outcome of a bounded autonomous episode."""

    succeeded: bool
    events: tuple[RuntimeEvent, ...]
    error: str | None = None


class _ProviderChain:
    """Provider failover without changing the provider contract."""

    def __init__(
        self,
        providers: Sequence[ReasoningProvider | LegacyPlanner],
        attempts_per_provider: int,
        emit,
    ) -> None:
        if not providers:
            raise ValueError("at least one reasoning provider is required")
        self._providers = tuple(providers)
        self._attempts = max(1, attempts_per_provider)
        self._emit = emit

    def decide(self, context: ReasoningContext) -> Decision:
        failures: list[str] = []
        for index, provider in enumerate(self._providers):
            for attempt in range(1, self._attempts + 1):
                try:
                    decision = self._call(provider, context)
                    self._emit(
                        RuntimeEvent(
                            phase="reason",
                            detail="provider decision accepted",
                            data={"provider_index": index, "attempt": attempt},
                        )
                    )
                    return decision
                except Exception as exc:
                    message = f"provider[{index}] attempt[{attempt}]: {exc}"
                    failures.append(message)
                    self._emit(
                        RuntimeEvent(
                            phase="reason",
                            detail="provider failed",
                            data={
                                "provider_index": index,
                                "attempt": attempt,
                                "error": str(exc),
                            },
                        )
                    )
        raise RuntimeError("all reasoning providers failed: " + " | ".join(failures))

    @staticmethod
    def _call(provider, context: ReasoningContext) -> Decision:
        decide = getattr(provider, "decide", None)
        if callable(decide):
            return decide(context)
        plan = getattr(provider, "plan", None)
        if callable(plan):
            return plan(context)
        raise TypeError("reasoning provider must implement decide() or legacy plan()")


class RuntimeBrain:
    """Bounded orchestration layer above the proven navigation kernel.

    The brain owns episode-level policy: provider resilience, lifecycle events,
    and safety limits. NavigationLoop remains responsible for the verified
    observe -> reason -> act -> fresh-observe -> verify -> evaluate cycle.
    """

    def __init__(
        self,
        bridge: NavigationBridge,
        providers: Sequence[ReasoningProvider | LegacyPlanner],
        *,
        config: RuntimeBrainConfig | None = None,
        evaluator: GoalEvaluator | None = None,
    ) -> None:
        self.bridge = bridge
        self.config = config or RuntimeBrainConfig()
        self.evaluator = evaluator or GoalEvaluator()
        self.events: list[RuntimeEvent] = []
        self._providers = _ProviderChain(
            providers,
            self.config.provider_attempts,
            self.events.append,
        )

    def run(self, goal: str) -> RuntimeBrainResult:
        self.events.clear()
        self.events.append(RuntimeEvent("start", "episode started", data={"goal": goal}))
        if not goal.strip():
            error = "goal must not be empty"
            self.events.append(RuntimeEvent("stop", error))
            return RuntimeBrainResult(False, tuple(self.events), error)

        try:
            self.events.append(RuntimeEvent("observe", "initial observation requested"))
            loop = NavigationLoop(
                bridge=self.bridge,
                planner=self._providers,
                evaluator=self.evaluator,
                max_steps=max(1, self.config.max_steps),
                settle_timeout=max(0.0, self.config.settle_timeout),
            )
            succeeded = loop.run(goal)
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
            self.events.append(RuntimeEvent("stop", "episode failed", data={"error": error}))
            return RuntimeBrainResult(False, tuple(self.events), error)

        if succeeded:
            self.events.append(RuntimeEvent("complete", "goal achieved"))
            return RuntimeBrainResult(True, tuple(self.events))

        error = "step budget exhausted"
        self.events.append(RuntimeEvent("stop", error))
        return RuntimeBrainResult(False, tuple(self.events), error)
