"""Small client for Google's Gemini generateContent API."""

import json
import os
import time
import urllib.error
import urllib.request


class GeminiClient:
    def __init__(
        self,
        model: str = "gemini-3.8-flash",
        fallback_model: str = "gemini-3.7-flash",
    ) -> None:
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise RuntimeError("Set GEMINI_API_KEY before starting the agent.")
        self.model = model
        self.fallback_model = fallback_model

    def ask(
        self,
        prompt: str,
        history: list[dict] | None = None,
        system_instruction: str | None = None,
    ) -> str:
        contents = list(history or []) + [{"role": "user", "parts": [{"text": prompt}]}]
        payload = {"contents": contents}
        if system_instruction:
            payload["system_instruction"] = {"parts": [{"text": system_instruction}]}
        body = json.dumps(payload).encode()

        models = [self.model]
        if self.fallback_model and self.fallback_model != self.model:
            models.append(self.fallback_model)

        last_error: RuntimeError | None = None
        for model_index, model in enumerate(models):
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={self.api_key}"
            )
            request = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"}, method="POST"
            )
            saw_503 = False
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(request, timeout=60) as response:
                        result = json.loads(response.read().decode())
                    break
                except urllib.error.HTTPError as exc:
                    details = exc.read().decode(errors="replace")
                    if exc.code == 503:
                        saw_503 = True
                    if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                        last_error = RuntimeError(
                            f"Gemini API error ({exc.code}): {details}"
                        )
                        break
                    time.sleep(2 ** attempt)
                except urllib.error.URLError as exc:
                    raise RuntimeError(f"Could not reach Gemini: {exc.reason}") from exc
            else:
                continue

            if "result" in locals():
                break
            if not (saw_503 and model_index + 1 < len(models)):
                raise last_error or RuntimeError("Gemini request failed.")

        try:
            return result["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Gemini returned an unexpected response: {result}") from exc
