from __future__ import annotations

from agent.runtime import create_reasoning_provider, create_task_runtime
from agent.deterministic_reasoner import DeterministicReasoner
from agent.task_runtime_clean import CleanTaskRuntime


def test_rebuild_has_one_runtime_owner():
    provider = create_reasoning_provider()
    assert isinstance(provider, DeterministicReasoner)
    runtime = create_task_runtime(object(), reasoning_provider=provider)
    assert isinstance(runtime, CleanTaskRuntime)
    assert runtime.planner is provider


def test_groq_is_only_a_reasoning_provider_at_composition_boundary(monkeypatch):
    class FakeTransport:
        def complete(self, prompt):
            return {"action_type": "wait", "target": None, "reason": "test"}

    def fake_transport(*, model=None, timeout=30.0, api_key=None):
        return FakeTransport()

    monkeypatch.setattr("agent.runtime.groq_transport", fake_transport)
    provider = create_reasoning_provider("groq", model="test-model", timeout=9.0)
    runtime = create_task_runtime(object(), reasoning_provider=provider)
    assert isinstance(runtime, CleanTaskRuntime)
    assert runtime.planner is provider
