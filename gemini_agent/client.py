"""Small client for Google's Gemini generateContent API."""

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable

from gemini_agent.tools import TOOL_DECLARATIONS, TOOL_HANDLERS


class GeminiClient:
    def __init__(
        self,
        model: str = "gemini-3.5-flash-lite",
        fallback_model: str = "gemini-3.5-flash",
        tool_handlers: dict[str, Callable[..., str]] | None = None,
    ) -> None:
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise RuntimeError("Set GEMINI_API_KEY before starting the agent.")
        self.model = model
        self.fallback_model = fallback_model
        self.groq_api_key = os.environ.get("GROQ_API_KEY")
        self.groq_model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")
        self.tool_handlers = {**TOOL_HANDLERS, **(tool_handlers or {})}
        self.web_search = os.environ.get("GEMINI_WEB_SEARCH", "").lower() in {"1", "true", "yes"}
        self.last_tool_calls: list[dict] = []
        self.last_grounding_sources: list[dict[str, str]] = []

    def _generate_gemini(
        self,
        contents: list[dict],
        system_instruction: str | None,
    ) -> dict:
        tools = [{"function_declarations": TOOL_DECLARATIONS}]
        if self.web_search:
            tools.append({"google_search": {}})
        payload = {
            "contents": contents,
            "tools": tools,
        }
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
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            result = None
            retryable_error = False

            for attempt in range(3):
                try:
                    with urllib.request.urlopen(request, timeout=60) as response:
                        result = json.loads(response.read().decode())
                    break
                except urllib.error.HTTPError as exc:
                    details = exc.read().decode(errors="replace")
                    if exc.code in (429, 500, 502, 503, 504):
                        retryable_error = True
                    if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                        last_error = RuntimeError(f"Gemini API error ({exc.code}): {details}")
                        break
                    time.sleep(2 ** attempt)
                except urllib.error.URLError as exc:
                    raise RuntimeError(f"Could not reach Gemini: {exc.reason}") from exc

            if result is not None:
                return result
            if retryable_error and model_index + 1 < len(models):
                continue
            break

        raise last_error or RuntimeError("Gemini request failed.")

    def _generate_groq(
        self,
        contents: list[dict],
        system_instruction: str | None,
    ) -> str:
        if not self.groq_api_key:
            raise RuntimeError("Gemini quota exhausted and GROQ_API_KEY is not configured.")

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        for item in contents:
            role = item.get("role")
            text_parts = [
                part["text"]
                for part in item.get("parts", [])
                if isinstance(part, dict) and "text" in part
            ]
            if role in {"user", "model"} and text_parts:
                messages.append({
                    "role": "assistant" if role == "model" else "user",
                    "content": "".join(text_parts),
                })

        payload = {
            "model": self.groq_model,
            "messages": messages,
        }
        if self.web_search:
            payload["tools"] = [{"type": "browser_search"}]
            payload["tool_choice"] = "required"

        for _ in range(3):
            request = urllib.request.Request(
                "https://api.groq.com/openai/v1/chat/completions",
                data=json.dumps(payload).encode(),
                headers={
                    "Authorization": f"Bearer {self.groq_api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    result = json.loads(response.read().decode())
            except urllib.error.HTTPError as exc:
                details = exc.read().decode(errors="replace")
                raise RuntimeError(f"Groq API error ({exc.code}): {details}") from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(f"Could not reach Groq: {exc.reason}") from exc

            try:
                message = result["choices"][0]["message"]
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError(f"Groq returned an unexpected response: {result}") from exc

            content = message.get("content")
            if content:
                return str(content)

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                raise RuntimeError(f"Groq returned an unexpected response: {result}")

            payload["messages"].append(message)
            for tool_call in tool_calls:
                payload["messages"].append({
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "content": "",
                })

        raise RuntimeError("Groq requested too many browser-search tool calls.")

    def _generate(
        self,
        contents: list[dict],
        system_instruction: str | None,
    ) -> dict | str:
        try:
            return self._generate_gemini(contents, system_instruction)
        except RuntimeError as exc:
            if self.groq_api_key and ("API error (429)" in str(exc) or "API error (503)" in str(exc)):
                return self._generate_groq(contents, system_instruction)
            raise

    def ask(
        self,
        prompt: str,
        history: list[dict] | None = None,
        system_instruction: str | None = None,
    ) -> str:
        contents = list(history or []) + [{"role": "user", "parts": [{"text": prompt}]}]
        self.last_tool_calls = []
        self.last_grounding_sources = []

        result = self._generate(contents, system_instruction)
        if isinstance(result, str):
            return result

        for _ in range(3):
            try:
                parts = result["candidates"][0]["content"]["parts"]
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError(f"Gemini returned an unexpected response: {result}") from exc

            function_call = next((part["functionCall"] for part in parts if "functionCall" in part), None)
            if function_call is None:
                metadata = result.get("candidates", [{}])[0].get("groundingMetadata", {})
                chunks = metadata.get("groundingChunks", [])
                self.last_grounding_sources = [
                    {
                        "title": str(chunk["web"].get("title", "Untitled")),
                        "uri": str(chunk["web"]["uri"]),
                    }
                    for chunk in chunks
                    if isinstance(chunk, dict)
                    and isinstance(chunk.get("web"), dict)
                    and chunk["web"].get("uri")
                ]
                try:
                    return "".join(part["text"] for part in parts if "text" in part)
                except (KeyError, TypeError) as exc:
                    raise RuntimeError(f"Gemini returned an unexpected response: {result}") from exc

            name = function_call.get("name")
            args = function_call.get("args", {})
            handler = self.tool_handlers.get(name)
            if handler is None:
                raise RuntimeError(f"Gemini requested an unknown tool: {name}")

            try:
                tool_result = handler(**args)
            except (KeyError, TypeError, ValueError) as exc:
                tool_result = f"Tool error: {exc}"

            call_trace = {"name": name, "args": args, "result": tool_result}
            if "expression" in args:
                call_trace["expression"] = str(args["expression"])
            self.last_tool_calls.append(call_trace)

            contents.extend([
                {"role": "model", "parts": parts},
                {"role": "user", "parts": [{"functionResponse": {"name": name, "response": {"result": tool_result}}}]},
            ])
            result = self._generate_gemini(contents, system_instruction)

        raise RuntimeError("Gemini requested too many tool calls.")
