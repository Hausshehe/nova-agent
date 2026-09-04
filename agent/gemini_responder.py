"""Minimal Gemini REST responder for Nova's v2 reasoning boundary."""

from __future__ import annotations

import json
import os
from typing import Any, Mapping
from urllib import error, request


DEFAULT_MODEL = "gemini-2.5-flash-lite"
DEFAULT_TIMEOUT_SECONDS = 20.0
GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

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
    "type": "OBJECT",
    "properties": {
        "action_type": {"type": "STRING", "enum": ["tap", "back", "scroll", "type", "swipe", "wait"]},
        "target_id": {"type": "STRING", "nullable": True},
        "value": {"type": "STRING", "nullable": True},
        "reason": {"type": "STRING"},
    },
    "required": ["action_type", "target_id", "value", "reason"],
}


class GeminiResponder:
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
        self._api_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY")
        self._model = model or os.environ.get("NOVA_GEMINI_MODEL", DEFAULT_MODEL)
        self._timeout_seconds = timeout_seconds
        self._opener = opener

    def __call__(self, prompt: str) -> Mapping[str, Any]:
        if not self._api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        if not prompt.strip():
            raise ValueError("reasoning prompt must not be blank")

        payload = {
            "system_instruction": {"parts": [{"text": _SYSTEM_INSTRUCTION}]},
            "contents": [{"role": "user", "parts": [{"text": f"Live Nova reasoning context:\n{prompt}"}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": _RESPONSE_SCHEMA,
            },
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        url = GEMINI_URL_TEMPLATE.format(model=self._model)
        req = request.Request(
            url,
            data=body,
            headers={
                "x-goog-api-key": self._api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with self._opener(req, timeout=self._timeout_seconds) as response:
                raw = response.read()
        except error.HTTPError as exc:
            raise RuntimeError(f"Gemini request failed with HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError("Gemini request failed") from exc
        except TimeoutError as exc:
            raise RuntimeError("Gemini request timed out") from exc

        try:
            envelope = json.loads(raw.decode("utf-8"))
            content = envelope["candidates"][0]["content"]["parts"][0]["text"]
            result = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Gemini returned an invalid reasoning response") from exc
        if not isinstance(result, Mapping):
            raise RuntimeError("Gemini reasoning response must be an object")
        return result
