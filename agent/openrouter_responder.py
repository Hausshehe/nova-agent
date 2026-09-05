"""Minimal OpenRouter HTTP responder for Nova's v2 reasoning boundary."""

from __future__ import annotations

import json
import os
from typing import Any, Mapping
from urllib import error, request


OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_TOKENS = 1024
USER_AGENT = "Nova-Agent/1.0"

_SYSTEM_INSTRUCTION = """You are Nova's Android navigation reasoning engine.
Return exactly one JSON object with these fields:
- action_type: one of tap, back, scroll, type, swipe, wait
- target_id: a live element id from the supplied observation, or null
- value: a string when required by the action, otherwise null
- reason: a short explanation
Never invent an element id. Use only the supplied observation. Choose the
smallest safe action that advances the user's goal. Nova will independently
validate your response before execution. Do not output markdown, commentary,
analysis, or any text outside the JSON object."""

_RESPONSE_FORMAT = {"type": "json_object"}


class OpenRouterResponder:
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
        self._api_key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY")
        self._model = model or os.environ.get("NOVA_OPENROUTER_MODEL", DEFAULT_MODEL)
        self._timeout_seconds = timeout_seconds
        self._opener = opener

    def __call__(self, prompt: str) -> Mapping[str, Any]:
        if not self._api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")
        if not prompt.strip():
            raise ValueError("reasoning prompt must not be blank")

        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": f"{_SYSTEM_INSTRUCTION}\n\nLive Nova reasoning context:\n{prompt}"}],
            "temperature": 0,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "response_format": _RESPONSE_FORMAT,
            "stream": False,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            OPENROUTER_CHAT_COMPLETIONS_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Connection": "close",
            },
            method="POST",
        )
        try:
            with self._opener(req, timeout=self._timeout_seconds) as response:
                raw = response.read()
        except error.HTTPError as exc:
            raise RuntimeError(f"OpenRouter request failed with HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError("OpenRouter request failed") from exc
        except TimeoutError as exc:
            raise RuntimeError("OpenRouter request timed out") from exc

        try:
            envelope = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"OpenRouter returned invalid JSON envelope: {raw[:500]!r}"
            ) from exc

        try:
            choice = envelope["choices"][0]
            message = choice["message"]
            content = message.get("content")
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                "OpenRouter response missing choices/message: "
                f"{json.dumps(envelope, ensure_ascii=False)[:1200]}"
            ) from exc

        if not isinstance(content, str) or not content.strip():
            reasoning = message.get("reasoning")
            reasoning_details = message.get("reasoning_details")
            finish_reason = choice.get("finish_reason")
            raise RuntimeError(
                "OpenRouter returned no usable reasoning content: "
                f"finish_reason={finish_reason!r}, "
                f"reasoning={str(reasoning)[:500]!r}, "
                f"reasoning_details={str(reasoning_details)[:800]!r}, "
                f"message_keys={list(message.keys())!r}"
            )

        try:
            result = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"OpenRouter returned non-JSON content: {content[:1000]!r}"
            ) from exc
        if not isinstance(result, Mapping):
            raise RuntimeError("OpenRouter reasoning response must be an object")
        return result
