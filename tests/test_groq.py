import pytest

from agent.groq import DEFAULT_GROQ_MODEL, GROQ_BASE_URL, groq_transport


def test_groq_transport_uses_environment(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_MODEL", "test-model")

    transport = groq_transport(timeout=9.0)

    assert transport.base_url == GROQ_BASE_URL
    assert transport.model == "test-model"
    assert transport.timeout == 9.0
    assert transport.api_key == "test-key"


def test_groq_transport_uses_default_model(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.delenv("GROQ_MODEL", raising=False)

    transport = groq_transport()

    assert transport.model == DEFAULT_GROQ_MODEL


def test_groq_transport_allows_explicit_values(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "environment-key")

    transport = groq_transport(
        model="explicit-model",
        timeout=4.0,
        api_key="explicit-key",
    )

    assert transport.model == "explicit-model"
    assert transport.timeout == 4.0
    assert transport.api_key == "explicit-key"


def test_groq_transport_requires_api_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="GROQ_API_KEY is not configured"):
        groq_transport()
