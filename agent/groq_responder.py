"""Minimal Groq HTTP responder for Nova's reasoning boundaries."""

from __future__ import annotations

import json
import os
from typing import Any, Mapping
from urllib import error, request


GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-20b"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_COMPLETION_TOKENS = 256
REPAIR_MAX_COMPLETION_TOKENS = 1024
USER_AGENT = "Nova-Agent/1.0"

_NAVIGATION_INSTRUCTION = """You are Nova's Android navigation reasoning engine.
Return exactly one JSON object with action_type, target_id, value, reason.
Use only live element ids from the observation. Never invent ids.
For a tap, target_id MUST be exactly one of the id values listed in observation.actions.
Do not create, transform, or infer an id from paths.
Choose one smallest safe action that advances the goal from the CURRENT state.
After each action, reassess the new UI state instead of assuming the next step.
Nova validates your decision before execution."""

_REPAIR_INSTRUCTION = """You are Nova's isolated self-repair proposal engine.
Return exactly one JSON object with description, patch, and paths.
You propose code only. You have NO authority to execute commands, choose tests,
modify the live repository, modify secrets, modify workflows, or approve adoption.
You have no authority to execute commands or choose validation commands.
Validation commands are selected by Nova's fixed validation policy, not by you.
The patch is applied only inside an isolated sandbox and is rejected if it fails
policy validation.

Return a minimal unified diff that is a complete, standard unified diff accepted
by `git apply`. For every changed file include both `--- a/path` and `+++ b/path`
headers and a valid unified-diff hunk header with line ranges, such as
`@@ -1,2 +1,2 @@`.
A valid one-line replacement looks like this:
`--- a/example.py\n+++ b/example.py\n@@ -1 +1 @@\n-old_value\n+new_value\n`
The patch string MUST end with a newline after the final changed line.
Replace the example paths and lines with the actual supplied source. Do not emit
an abbreviated diff, prose around the diff, markdown fences, or an `@@` header
without valid line ranges. Paths must exactly match the paths list.
Make the smallest change that directly addresses the supplied failure evidence.
Never modify files outside the supplied source evidence unless the evidence
explicitly contains them. Do not modify secrets, workflows, binaries, or config.
"""

_REPAIR_DIFF_RETRY_INSTRUCTION = """Your previous repair proposal contained invalid unified-diff formatting.
Return the same repair proposal again, but correct ONLY the patch formatting.
Every hunk header MUST contain valid line ranges, for example `@@ -1,2 +1,2 @@`.
Do not use a bare `@@`. The patch string MUST end with a newline after the final
changed line. Do not change the intended code fix, paths, or description.
Return exactly one JSON object with description, patch, and paths.
The patch must be a complete standard unified diff accepted by `git apply`.
"""

_RESPONSE_SCHEMAS = {
    "reasoning": {
        "type": "json_schema",
        "json_schema": {
            "name": "nova_navigation_decision",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "action_type": {"type": "string", "enum": ["tap", "back", "scroll", "type", "swipe", "wait"]},
                    "target_id": {"type": ["string", "null"]},
                    "value": {"type": ["string", "null"]},
                    "reason": {"type": "string"},
                },
                "required": ["action_type", "target_id", "value", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "repair": {
        "type": "json_schema",
        "json_schema": {
            "name": "nova_repair_proposal",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "patch": {"type": "string"},
                    "paths": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["description", "patch", "paths"],
                "additionalProperties": False,
            },
        },
    },
}


def _http_error_detail(exc: error.HTTPError) -> str:
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


def _repair_patch_needs_retry(result: Mapping[str, Any]) -> bool:
    patch = result.get("patch")
    if not isinstance(patch, str):
        return False
    for line in patch.splitlines():
        if line.startswith("@@") and not line.startswith("@@ -"):
            return True
    return not patch.endswith("\n")


class GroqResponder:
    """Callable adapter from Nova's prompt string to a structured mapping."""

    def __init__(self, api_key=None, model=None, timeout_seconds=DEFAULT_TIMEOUT_SECONDS, opener=request.urlopen, task="reasoning"):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if task not in _RESPONSE_SCHEMAS:
            raise ValueError(f"task must be one of: {', '.join(_RESPONSE_SCHEMAS)}")
        self._api_key = api_key if api_key is not None else os.environ.get("GROQ_API_KEY")
        self._model = model or os.environ.get("NOVA_GROQ_MODEL", DEFAULT_MODEL)
        self._timeout_seconds = timeout_seconds
        self._opener = opener
        self._task = task

    def _request(self, instruction: str, prompt: str) -> Mapping[str, Any]:
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": f"{instruction}\n\nLive Nova context:\n{prompt}"}],
            "temperature": 0,
            "reasoning_effort": "low",
            "max_completion_tokens": REPAIR_MAX_COMPLETION_TOKENS if self._task == "repair" else DEFAULT_MAX_COMPLETION_TOKENS,
            "response_format": _RESPONSE_SCHEMAS[self._task],
            "stream": False,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(GROQ_CHAT_COMPLETIONS_URL, data=body, headers={
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }, method="POST")
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
            raise RuntimeError(f"Groq returned an invalid {self._task} response") from exc
        if not isinstance(result, Mapping):
            raise RuntimeError(f"Groq {self._task} response must be an object")
        return result

    def __call__(self, prompt: str) -> Mapping[str, Any]:
        if not self._api_key:
            raise RuntimeError("GROQ_API_KEY is not set")
        if not prompt.strip():
            raise ValueError(f"{self._task} prompt must not be blank")
        instruction = _REPAIR_INSTRUCTION if self._task == "repair" else _NAVIGATION_INSTRUCTION
        result = self._request(instruction, prompt)
        if self._task == "repair" and _repair_patch_needs_retry(result):
            result = self._request(_REPAIR_DIFF_RETRY_INSTRUCTION, prompt)
        return result
