"""Build Nova's v2 runtime from the capability-provider boundary.

This module is the narrow seam between provider construction and the platform
runtime. Providers are supplied as responder callables; capability eligibility
and bounded routing remain owned by the provider catalog/factory. Android stays
behind the Observer/Executor ports.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from agent.capability import Capability
from agent.capability_config import build_capability_router
from agent.provider_pool import Responder

from .capability_reasoner import CapabilityRoutedReasoner
from .llm_planner import LLMPlanner
from .models import Goal
from .ports import Executor, Observer, Verifier
from .runtime import Runtime


def build_capability_runtime(
    goal: Goal,
    observer: Observer,
    executor: Executor,
    verifier: Verifier,
    *,
    action_responders: Sequence[tuple[str, Responder]],
    planning_responders: Sequence[tuple[str, Responder]] = (),
    pool_kwargs: Mapping[str, object] | None = None,
    max_steps: int = 20,
    max_invalid_decisions: int = 3,
    max_replans: int = 2,
    **runtime_kwargs: Any,
) -> Runtime:
    """Construct the normal v2 runtime with capability-routed AI boundaries.

    Action selection and planning share one capability router but retain
    independent provider-pool health. Missing planning support simply disables
    the planner. Perception and verification are intentionally not fabricated
    here: Android observation and the supplied verifier remain authoritative.
    """

    router = build_capability_router(
        {
            Capability.ACTION_SELECTION: action_responders,
            Capability.PLANNING: planning_responders,
        },
        pool_kwargs=pool_kwargs,
    )

    reasoner = CapabilityRoutedReasoner(router)
    planner = None
    if router.providers(Capability.PLANNING):
        planner = LLMPlanner(
            lambda prompt: __import__("json").dumps(
                router(Capability.PLANNING, prompt),
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )

    return Runtime(
        goal,
        observer,
        reasoner,
        executor,
        verifier,
        max_steps=max_steps,
        max_invalid_decisions=max_invalid_decisions,
        max_replans=max_replans,
        planner=planner,
        **runtime_kwargs,
    )
