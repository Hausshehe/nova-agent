from __future__ import annotations

from typing import Literal

from .deterministic_reasoner import DeterministicReasoner
from .groq import groq_transport
from .llm_reasoning_provider import LLMReasoningProvider
from .reasoning_provider import ReasoningProvider
from .task_runtime_clean import CleanTaskRuntime

ProviderName = Literal["deterministic", "groq"]


def create_reasoning_provider(provider: ProviderName = "deterministic", *, model: str | None = None, timeout: float = 30.0) -> ReasoningProvider:
    if provider == "deterministic":
        return DeterministicReasoner()
    if provider == "groq":
        return LLMReasoningProvider(groq_transport(model=model, timeout=timeout).complete)
    raise ValueError(f"unsupported reasoning provider: {provider}")


def create_task_runtime(
    bridge,
    *,
    provider: ProviderName = "deterministic",
    reasoning_provider: ReasoningProvider | None = None,
    model: str | None = None,
    provider_timeout: float = 30.0,
    max_steps: int = 5,
    settle_timeout: float = 2.0,
) -> CleanTaskRuntime:
    selected = reasoning_provider or create_reasoning_provider(provider, model=model, timeout=provider_timeout)
    return CleanTaskRuntime(bridge=bridge, planner=selected, max_steps=max_steps, settle_timeout=settle_timeout)
