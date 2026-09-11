"""Minimal Cerebras OpenAI-compatible responder for Nova's v2 reasoning boundary."""

from __future__ import annotations

import json
import os
from typing import Any, Mapping
from urllib import error, request

CEREBRAS_CHAT_COMPLETIONS_URL = "https://api.cerebras.ai/v1/chat/completions"
DEFAULT_MODEL = "gpt-oss-120b"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_COMPLETION_TOKENS = 256
USER_AGENT = "Nova-Agent/1.0"

_NAVIGATION_INSTRUCTION = """You are Nova's Android navigation reasoning engine.
Return exactly one JSON object with action_type, target_id, value, reason.
action_type must be tap, back, scroll, type, swipe, or wait. Use only live ids
from the observation. Never invent an id. Choose the smallest safe action."""
_PLANNING_INSTRUCTION = """You are Nova's mission planning engine.
Return exactly one JSON object with a steps array of short, non-empty mission
intent strings. Produce intents, not concrete UI actions or element ids. Keep the
plan focused on the goal and current evidence."""

_RESPONSE_SCHEMAS = {
    "reasoning": {"type": "json_schema", "json_schema": {"name": "nova_navigation_decision", "strict": True, "schema": {"type": "object", "properties": {"action_type": {"type": "string", "enum": ["tap", "back", "scroll", "type", "swipe", "wait"]}, "target_id": {"type": ["string", "null"]}, "value": {"type": ["string", "null"]}, "reason": {"type": "string"}}, "required": ["action_type", "target_id", "value", "reason"], "additionalProperties": False}}},
    "planning": {"type": "json_schema", "json_schema": {"name": "nova_mission_plan", "strict": True, "schema": {"type": "object", "properties": {"steps": {"type": "array", "items": {"type": "string", "minLength": 1}}}, "required": ["steps"], "additionalProperties": False}}},
}


class CerebrasResponder:
    """Callable adapter for Nova reasoning and mission-planning responses."""

    def __init__(self, api_key: str | None = None, model: str | None = None,
                 timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS, opener=request.urlopen,
                 task: str = "reasoning") -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if task not in _RESPONSE_SCHEMAS:
            raise ValueError("task must be 'reasoning' or 'planning'")
        self._api_key = api_key if api_key is not None else os.environ.get("CEREBRAS_API_KEY")
        self._model = model or os.environ.get("NOVA_CEREBRAS_MODEL", DEFAULT_MODEL)
        self._timeout_seconds = timeout_seconds
        self._opener = opener
        self._task = task

    def __call__(self, prompt: str) -> Mapping[str, Any]:
        if not self._api_key:
            raise RuntimeError("CEREBRAS_API_KEY is not set")
        if not prompt.strip():
            raise ValueError(f"{self._task} prompt must not be blank")
        instruction = _PLANNING_INSTRUCTION if self._task == "planning" else _NAVIGATION_INSTRUCTION
        payload = {"model": self._model, "messages": [{"role": "user", "content": f"{instruction}\n\nLive Nova context:\n{prompt}"}], "temperature": 0, "max_completion_tokens": DEFAULT_MAX_COMPLETION_TOKENS, "response_format": _RESPONSE_SCHEMAS[self._task], "stream": False}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(CEREBRAS_CHAT_COMPLETIONS_URL, data=body, headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json", "User-Agent": USER_AGENT, "Accept": "application/json"}, method="POST")
        try:
            with self._opener(req, timeout=self._timeout_seconds) as response:
                raw = response.read()
        except error.HTTPError as exc:
            raise RuntimeError(f"Cerebras request failed with HTTP {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError("Cerebras request failed") from exc
        except TimeoutError as exc:
            raise RuntimeError("Cerebras request timed out") from exc
        try:
            envelope = json.loads(raw.decode("utf-8"))
            content = envelope["choices"][0]["message"]["content"]
            result = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Cerebras returned an invalid {self._task} response") from exc
        if not isinstance(result, Mapping):
            raise RuntimeError(f"Cerebras {self._task} response must be an object")
        return result
