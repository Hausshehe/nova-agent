from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any, Mapping


class LLMTransportError(RuntimeError):
    """Raised when an LLM transport cannot produce a usable response."""


@dataclass(frozen=True)
class OpenAICompatibleTransport:
    """Minimal stdlib-only client for an OpenAI-compatible chat endpoint.

    The transport knows nothing about Nova actions. It only sends messages and
    returns the assistant message content. Response validation remains inside
    Nova's reasoning provider.
    """

    base_url: str
    model: str
    timeout: float = 30.0
    api_key: str | None = None

    def complete(self, prompt: str) -> Mapping[str, Any]:
        url = self.base_url.rstrip("/") + "/v1/chat/completions"
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = Request(
            url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            raise LLMTransportError(f"LLM HTTP error: {exc.code}") from exc
        except URLError as exc:
            raise LLMTransportError("LLM connection failed") from exc
        except TimeoutError as exc:
            raise LLMTransportError("LLM request timed out") from exc

        try:
            payload = json.loads(raw)
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMTransportError("LLM response has unexpected shape") from exc

        if not isinstance(content, str):
            raise LLMTransportError("LLM message content must be text")

        try:
            result = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMTransportError("LLM message content is not valid JSON") from exc

        if not isinstance(result, Mapping):
            raise LLMTransportError("LLM JSON response must be an object")
        return result
