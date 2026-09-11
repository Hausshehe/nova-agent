"""Minimal Gemini REST responder for Nova's v2 reasoning boundary."""

from __future__ import annotations

import json
import os
from typing import Any, Mapping
from urllib import error, request

DEFAULT_MODEL = "gemini-3.6-flash"
DEFAULT_TIMEOUT_SECONDS = 60.0
GEMINI_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

_NAVIGATION_INSTRUCTION = """You are Nova's Android navigation reasoning engine.
Return exactly one JSON object with these fields:
action_type, target_id, value, reason.
action_type must be one of tap, back, scroll, type, swipe, wait.
Use only live ids from the observation. Never invent an id. Choose the smallest
safe action that advances the goal. Nova validates the response before execution."""
_PLANNING_INSTRUCTION = """You are Nova's mission planning engine.
Return exactly one JSON object with a steps array of short, non-empty mission
intent strings. Produce intents, not concrete UI actions or element ids. Keep the
plan focused on the goal and current evidence. Nova validates and bounds the plan."""

_RESPONSE_SCHEMAS = {
    "reasoning": {
        "type": "OBJECT",
        "properties": {
            "action_type": {"type": "STRING", "enum": ["tap", "back", "scroll", "type", "swipe", "wait"]},
            "target_id": {"type": "STRING", "nullable": True},
            "value": {"type": "STRING", "nullable": True},
            "reason": {"type": "STRING"},
        },
        "required": ["action_type", "target_id", "value", "reason"],
    },
    "planning": {
        "type": "OBJECT",
        "properties": {"steps": {"type": "ARRAY", "items": {"type": "STRING"}}},
        "required": ["steps"],
    },
}


class GeminiResponder:
    """Callable adapter for Nova reasoning and mission-planning responses."""

    def __init__(self, api_key: str | None = None, model: str | None = None,
                 timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS, opener=request.urlopen,
                 task: str = "reasoning") -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if task not in _RESPONSE_SCHEMAS:
            raise ValueError("task must be 'reasoning' or 'planning'")
        self._api_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY")
        self._model = model or os.environ.get("NOVA_GEMINI_MODEL", DEFAULT_MODEL)
        self._timeout_seconds = timeout_seconds
        self._opener = opener
        self._task = task

    def __call__(self, prompt: str) -> Mapping[str, Any]:
        if not self._api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        if not prompt.strip():
            raise ValueError(f"{self._task} prompt must not be blank")
        instruction = _PLANNING_INSTRUCTION if self._task == "planning" else _NAVIGATION_INSTRUCTION
        payload = {
            "system_instruction": {"parts": [{"text": instruction}]},
            "contents": [{"role": "user", "parts": [{"text": f"Live Nova context:\n{prompt}"}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "responseSchema": _RESPONSE_SCHEMAS[self._task]},
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(GEMINI_URL_TEMPLATE.format(model=self._model), data=body,
                              headers={"x-goog-api-key": self._api_key, "Content-Type": "application/json", "Accept": "application/json"}, method="POST")
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
            raise RuntimeError(f"Gemini returned an invalid {self._task} response") from exc
        if not isinstance(result, Mapping):
            raise RuntimeError(f"Gemini {self._task} response must be an object")
        return result
