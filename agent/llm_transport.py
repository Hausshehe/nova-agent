from __future__ import annotations

import json
import time
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
    max_rate_limit_retries: int = 2
    max_rate_limit_wait: float = 10.0

    def complete(self, prompt: str) -> Mapping[str, Any]:
        url = self.base_url.rstrip("/") + "/v1/chat/completions"
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": "Respond with a valid JSON object.\n\n" + prompt,
                }
            ],
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Nova-Agent/1.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = Request(
            url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        rate_limit_attempts = 0
        while True:
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8")
                break
            except HTTPError as exc:
                if exc.code != 429 or rate_limit_attempts >= self.max_rate_limit_retries:
                    detail = self._http_error_detail(exc)
                    suffix = f": {detail}" if detail else ""
                    raise LLMTransportError(f"LLM HTTP error: {exc.code}{suffix}") from exc

                wait_seconds = self._retry_after_seconds(exc)
                if wait_seconds is None or wait_seconds > self.max_rate_limit_wait:
                    detail = self._http_error_detail(exc)
                    suffix = f": {detail}" if detail else ""
                    raise LLMTransportError(
                        f"LLM rate limited (429); retry-after unavailable or too long{suffix}"
                    ) from exc

                rate_limit_attempts += 1
                time.sleep(wait_seconds)
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

    @staticmethod
    def _retry_after_seconds(exc: HTTPError) -> float | None:
        value = exc.headers.get("Retry-After") if exc.headers else None
        if value is None:
            return None
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            return None
        return seconds if seconds >= 0 else None

    @staticmethod
    def _http_error_detail(exc: HTTPError) -> str | None:
        try:
            raw = exc.read().decode("utf-8")
        except Exception:
            return None
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return raw[:200]
        error = payload.get("error") if isinstance(payload, Mapping) else None
        if isinstance(error, Mapping):
            message = error.get("message") or error.get("code")
            return str(message) if message else None
        return None
