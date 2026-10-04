"""Small client for Google's Gemini generateContent API."""

import json
import os
import time
import urllib.error
import urllib.request


class GeminiClient:
    def __init__(self, model: str = "gemini-3.8-flash") -> None:
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise RuntimeError("Set GEMINI_API_KEY before starting the agent.")
        self.model = model

    def ask(self, prompt: str, history: list[dict] | None = None) -> str:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        contents = list(history or []) + [{"role": "user", "parts": [{"text": prompt}]}]
        body = json.dumps({"contents": contents}).encode()
        request = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    result = json.loads(response.read().decode())
                break
            except urllib.error.HTTPError as exc:
                details = exc.read().decode(errors="replace")
                if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise RuntimeError(f"Gemini API error ({exc.code}): {details}") from exc
                time.sleep(2 ** attempt)
            except urllib.error.URLError as exc:
                raise RuntimeError(f"Could not reach Gemini: {exc.reason}") from exc

        try:
            return result["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Gemini returned an unexpected response: {result}") from exc
