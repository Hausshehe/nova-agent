from __future__ import annotations

import os

from .llm_transport import OpenAICompatibleTransport

GROQ_BASE_URL = "https://api.groq.com/openai"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"


def groq_transport(
    *,
    model: str | None = None,
    timeout: float = 30.0,
    api_key: str | None = None,
) -> OpenAICompatibleTransport:
    """Build a Groq transport from explicit values or environment configuration.

    The API key is read at runtime and is never part of Nova's source tree.
    """
    key = api_key if api_key is not None else os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not configured")

    selected_model = model or os.environ.get("GROQ_MODEL", DEFAULT_GROQ_MODEL)
    return OpenAICompatibleTransport(
        base_url=GROQ_BASE_URL,
        model=selected_model,
        timeout=timeout,
        api_key=key,
    )
