from __future__ import annotations

import json
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any, Mapping


class LLMTransportError(RuntimeError):
    pass


@dataclass(frozen=True)
class OpenAICompatibleTransport:
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
            "messages": [{"role": "user", "content": "Respond with a valid JSON object.\n\n" + prompt}],
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        headers = {"Content-Type": "application/json", "User-Agent": "Nova-Agent/1.0"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(url, data=json.dumps(body, ensure_ascii=False).encode(), headers=headers, method="POST")
        attempts = 0
        while True:
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8")
                break
            except HTTPError as exc:
                if exc.code != 429 or attempts >= self.max_rate_limit_retries:
                    raise LLMTransportError(f"LLM HTTP error: {exc.code}") from exc
                wait = self._retry_after_seconds(exc)
                if wait is None or wait > self.max_rate_limit_wait:
                    raise LLMTransportError("LLM rate limited with no safe retry interval") from exc
                attempts += 1
                time.sleep(wait)
            except URLError as exc:
                raise LLMTransportError("LLM connection failed") from exc
            except TimeoutError as exc:
                raise LLMTransportError("LLM request timed out") from exc
        try:
            content = json.loads(raw)["choices"][0]["message"]["content"]
            result = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMTransportError("LLM response has unexpected JSON shape") from exc
        if not isinstance(result, Mapping):
            raise LLMTransportError("LLM JSON response must be an object")
        return result

    @staticmethod
    def _retry_after_seconds(exc: HTTPError) -> float | None:
        value = exc.headers.get("Retry-After") if exc.headers else None
        try:
            return float(value) if value is not None and float(value) >= 0 else None
        except (TypeError, ValueError):
            return None
