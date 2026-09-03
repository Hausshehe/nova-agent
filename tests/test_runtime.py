from __future__ import annotations

import pytest

from agent.deterministic_reasoner import DeterministicReasoner
from agent.llm_reasoning_provider import LLMReasoningProvider
from agent.runtime import create_reasoning_provider, create_task_executor
from agent.task_runtime import TaskExecutor


class FakeBridge:
    pass


def test_default_runtime_uses_deterministic_provider():
    provider = create_reasoning_provider()

    assert isinstance(provider, DeterministicReasoner)


def test_task_executor_is_built_around_selected_provider():
    runtime = create_task_executor(FakeBridge(), max_steps=7, settle_timeout=1.5)

    assert isinstance(runtime, TaskExecutor)
    assert isinstance(runtime.planner, DeterministicReasoner)
    assert runtime.max_steps == 7
    assert runtime.settle_timeout == 1.5


def test_groq_runtime_provider_is_constructed_at_boundary(monkeypatch):
    class FakeTransport:
        def complete(self, prompt: str):
            return {"action_type": "wait", "target": None, "reason": "test"}

    captured = {}

    def fake_groq_transport(*, model=None, timeout=30.0, api_key=None):
        captured.update(model=model, timeout=timeout)
        return FakeTransport()

    monkeypatch.setattr("agent.runtime.groq_transport", fake_groq_transport)

    provider = create_reasoning_provider("groq", model="test-model", timeout=12.0)

    assert isinstance(provider, LLMReasoningProvider)
    assert captured == {"model": "test-model", "timeout": 12.0}


def test_unsupported_provider_is_rejected():
    with pytest.raises(ValueError, match="unsupported reasoning provider"):
        create_reasoning_provider("unknown")
