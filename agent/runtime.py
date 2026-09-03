from __future__ import annotations

from typing import Literal

from .core import WorldState
from .deterministic_reasoner import DeterministicReasoner
from .groq import groq_transport
from .llm_reasoning_provider import LLMReasoningProvider
from .reasoning_provider import ReasoningProvider
from .task_runtime import TaskExecutor

ProviderName = Literal["deterministic", "groq"]


def create_reasoning_provider(
    provider: ProviderName = "deterministic",
    *,
    model: str | None = None,
    timeout: float = 30.0,
) -> ReasoningProvider:
    """Construct Nova's selected reasoning provider at the runtime boundary."""
    if provider == "deterministic":
        return DeterministicReasoner()
    if provider == "groq":
        transport = groq_transport(model=model, timeout=timeout)
        return LLMReasoningProvider(transport.complete)
    raise ValueError(f"unsupported reasoning provider: {provider}")


def create_task_executor(
    bridge,
    *,
    provider: ProviderName = "deterministic",
    model: str | None = None,
    provider_timeout: float = 30.0,
    max_steps: int = 5,
    settle_timeout: float = 2.0,
) -> TaskExecutor:
    """Build the canonical Nova task runtime from a selected provider."""
    reasoning_provider = create_reasoning_provider(
        provider,
        model=model,
        timeout=provider_timeout,
    )
    return TaskExecutor(
        bridge=bridge,
        planner=reasoning_provider,
        max_steps=max_steps,
        settle_timeout=settle_timeout,
    )
