"""Small client for Google's Gemini generateContent API."""

import json
import os
import time
import urllib.error
import urllib.request

from gemini_agent.tools import calculator


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
        self.last_tool_calls: list[dict] = []

    def _generate(
        self,
        contents: list[dict],
        system_instruction: str | None,
    ) -> dict:
        payload = {
            "contents": contents,
            "tools": [{
                "function_declarations": [{
                    "name": "calculator",
                    "description": "Calculate basic arithmetic expressions.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "expression": {
                                "type": "STRING",
                                "description": "A basic arithmetic expression using numbers and +, -, *, /, %, and parentheses.",
                            }
                        },
                        "required": ["expression"],
                    },
                }]
            }],
        }
        if system_instruction:
            payload["system_instruction"] = {"parts": [{"text": system_instruction}]}
        body = json.dumps(payload).encode()

        models = [self.model]
        if self.fallback_model and self.fallback_model != self.model:
            models.append(self.fallback_model)

        for model_index, model in enumerate(models):
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={self.api_key}"
            )
            request = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"}, method="POST"
            )
            saw_503 = False
            result = None
            last_error: RuntimeError | None = None

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

            if result is not None:
                return result
            if not (saw_503 and model_index + 1 < len(models)):
                raise last_error or RuntimeError("Gemini request failed.")

        raise RuntimeError("Gemini request failed.")

    def ask(
        self,
        prompt: str,
        history: list[dict] | None = None,
        system_instruction: str | None = None,
    ) -> str:
        contents = list(history or []) + [{"role": "user", "parts": [{"text": prompt}]}]
        self.last_tool_calls = []

        for _ in range(3):
            result = self._generate(contents, system_instruction)
            try:
                parts = result["candidates"][0]["content"]["parts"]
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError(
                    f"Gemini returned an unexpected response: {result}"
                ) from exc

            function_call = next(
                (part["functionCall"] for part in parts if "functionCall" in part),
                None,
            )
            if function_call is None:
                try:
                    return "".join(part["text"] for part in parts if "text" in part)
                except (KeyError, TypeError) as exc:
                    raise RuntimeError(
                        f"Gemini returned an unexpected response: {result}"
                    ) from exc

            name = function_call.get("name")
            args = function_call.get("args", {})
            if name != "calculator":
                raise RuntimeError(f"Gemini requested an unknown tool: {name}")

            expression = str(args.get("expression", ""))
            try:
                tool_result = calculator(expression)
            except (KeyError, TypeError, ValueError) as exc:
                tool_result = f"Tool error: {exc}"

            self.last_tool_calls.append({
                "name": name,
                "expression": expression,
                "result": tool_result,
            })

            contents.extend([
                {"role": "model", "parts": parts},
                {
                    "role": "user",
                    "parts": [{
                        "functionResponse": {
                            "name": name,
                            "response": {"result": tool_result},
                        }
                    }],
                },
            ])

        raise RuntimeError("Gemini requested too many tool calls.")
