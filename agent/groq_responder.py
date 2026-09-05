"""Minimal Groq HTTP responder for Nova's v2 reasoning boundary.

This module owns only provider transport and response decoding. It does not
choose targets, execute actions, retry requests, or orchestrate providers.
"""

from __future__ import annotations

import json
import os
from typing import Any, Mapping
from urllib import error, request


GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-20b"
DEFAULT_TIMEOUT_SECONDS = 20.0
USER_AGENT = "Nova-Agent/1.0"

_SYSTEM_INSTRUCTION = """You are Nova's Android navigation reasoning engine.
Return exactly one JSON object with these fields:
- action_type: one of tap, back, scroll, type, swipe, wait
- target_id: a live element id from the supplied observation, or null
- value: a string when required by the action, otherwise null
- reason: a short explanation
Never invent an element id. Use only the supplied observation. Choose the
smallest safe action that advances the user's goal. Nova will independently
validate your response before execution."""

_RESPONSE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "nova_navigation_decision",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "action_type": {
                    "type": "string",
                    "enum": ["tap", "back", "scroll", "type", "swipe", "wait"],
                },
                "target_id": {"type": ["string", "null"]},
                "value": {"type": ["string", "null"]},
                "reason": {"type": "string"},
            },
            "required": ["action_type", "target_id", "value", "reason"],
            "additionalProperties": False,
        },
    },
}


def _http_error_detail(exc: error.HTTPError) -> str:
    """Return a compact provider error detail without exposing credentials."""
    try:
        raw = exc.read().decode("utf-8", errors="replace")
        payload = json.loads(raw)
        if isinstance(payload, Mapping):
            provider_error = payload.get("error")
            if isinstance(provider_error, Mapping):
                message = provider_error.get("message")
                code = provider_error.get("code")
                parts = [str(part) for part in (message, code) if part]
                if parts:
                    return ": ".join(parts)
            message = payload.get("message")
            if message:
                return str(message)
        return raw.strip()[:300]
    except Exception:
        return ""


class GroqResponder:
    """Callable adapter from Nova's prompt string to a structured mapping."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        opener=request.urlopen,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._api_key = api_key if api_key is not None else os.environ.get("GROQ_API_KEY")
        self._model = model or os.environ.get("NOVA_GROQ_MODEL", DEFAULT_MODEL)
        self._timeout_seconds = timeout_seconds
        self._opener = opener

    def __call__(self, prompt: str) -> Mapping[str, Any]:
        if not self._api_key:
            raise RuntimeError("GROQ_API_KEY is not set")
        if not prompt.strip():
            raise ValueError("reasoning prompt must not be blank")

        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": f"{_SYSTEM_INSTRUCTION}\n\nLive Nova reasoning context:\n{prompt}",
                }
            ],
            "temperature": 0,
            "reasoning_effort": "low",
            "max_completion_tokens": 512,
            "response_format": _RESPONSE_SCHEMA,
            "stream": False,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            GROQ_CHAT_COMPLETIONS_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with self._opener(req, timeout=self._timeout_seconds) as response:
                raw = response.read()
        except error.HTTPError as exc:
            detail = _http_error_detail(exc)
            suffix = f": {detail}" if detail else ""
            raise RuntimeError(f"Groq request failed with HTTP {exc.code}{suffix}") from exc
        except error.URLError as exc:
            raise RuntimeError("Groq request failed") from exc
        except TimeoutError as exc:
            raise RuntimeError("Groq request timed out") from exc

        try:
            envelope = json.loads(raw.decode("utf-8"))
            content = envelope["choices"][0]["message"]["content"]
            result = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Groq returned an invalid reasoning response") from exc

        if not isinstance(result, Mapping):
            raise RuntimeError("Groq reasoning response must be an object")
        return result
