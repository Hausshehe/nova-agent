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
        self.openrouter_api_key = os.environ.get("OPENROUTER_API_KEY")
        self.openrouter_model = os.environ.get("OPENROUTER_MODEL", "openrouter/free")
        self.cloudflare_api_token = os.environ.get("CLOUDFLARE_API_TOKEN")
        self.cloudflare_account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        self.cloudflare_model = os.environ.get(
            "CLOUDFLARE_MODEL", "@cf/zai-org/glm-4.7-flash"
        )
        self.tool_handlers = {**TOOL_HANDLERS, **(tool_handlers or {})}
        self.web_search = os.environ.get("GEMINI_WEB_SEARCH", "").lower() in {"1", "true", "yes"}
        self.last_tool_calls: list[dict] = []
        self.last_grounding_sources: list[dict[str, str]] = []
        self._disabled_providers: set[str] = set()

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

    @staticmethod
    def _groq_parameters(parameters: dict) -> dict:
        """Convert Gemini tool-schema type names to standard JSON Schema."""
        converted = json.loads(json.dumps(parameters))
        if isinstance(converted, dict):
            def convert(node):
                if isinstance(node, dict):
                    if isinstance(node.get("type"), str):
                        node["type"] = node["type"].lower()
                    for value in node.values():
                        convert(value)
                elif isinstance(node, list):
                    for value in node:
                        convert(value)
            convert(converted)
        return converted

    @staticmethod
    def _parse_tool_arguments(arguments) -> dict:
        """Accept JSON-string or already-decoded tool arguments from fallbacks."""
        if arguments in (None, ""):
            return {}
        if isinstance(arguments, dict):
            return arguments
        parsed = json.loads(arguments)
        if not isinstance(parsed, dict):
            raise ValueError("Tool arguments must be a JSON object.")
        return parsed

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

        if self.web_search:
            tools = [{"type": "browser_search"}]
        else:
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": declaration["name"],
                        "description": declaration["description"],
                        "parameters": self._groq_parameters(declaration["parameters"]),
                    },
                }
                for declaration in TOOL_DECLARATIONS
            ]

        payload = {
            "model": self.groq_model,
            "messages": messages,
            "max_tokens": 1024,
            "tools": tools,
        }
        if self.web_search:
            payload["tool_choice"] = "required"

        for _ in range(3):
            request = urllib.request.Request(
                "https://api.groq.com/openai/v1/chat/completions",
                data=json.dumps(payload).encode(),
                headers={
                    "Authorization": f"Bearer {self.groq_api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "curl/8.0",
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
                function = tool_call.get("function") or {}
                name = function.get("name")
                handler = self.tool_handlers.get(name)
                if handler is None:
                    raise RuntimeError(f"Groq requested an unknown tool: {name}")

                try:
                    args = self._parse_tool_arguments(function.get("arguments", "{}"))
                    tool_result = handler(**args)
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                    args = {}
                    tool_result = f"Tool error: {exc}"

                call_trace = {"name": name, "args": args, "result": tool_result}
                if "expression" in args:
                    call_trace["expression"] = str(args["expression"])
                self.last_tool_calls.append(call_trace)

                payload["messages"].append({
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "content": str(tool_result),
                })

        raise RuntimeError("Groq requested too many browser-search tool calls.")

    def _generate_cloudflare(
        self,
        contents: list[dict],
        system_instruction: str | None,
    ) -> str:
        if not self.cloudflare_api_token or not self.cloudflare_account_id:
            raise RuntimeError(
                "Cloudflare credentials are not configured."
            )

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

        requested_tool = self._requested_local_tool(contents)
        declarations = TOOL_DECLARATIONS
        if requested_tool:
            declarations = [
                declaration
                for declaration in TOOL_DECLARATIONS
                if declaration["name"] == requested_tool
            ]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": declaration["name"],
                    "description": declaration["description"],
                    "parameters": self._groq_parameters(declaration["parameters"]),
                },
            }
            for declaration in declarations
        ]
        payload = {
            "model": self.cloudflare_model,
            "messages": messages,
            "max_tokens": 1024,
            "tools": tools,
        }
        if requested_tool:
            payload["tool_choice"] = {
                "type": "function",
                "function": {"name": requested_tool},
            }
        elif self._requires_local_tool(contents):
            payload["tool_choice"] = "required"

        url = (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{self.cloudflare_account_id}/ai/v1/chat/completions"
        )
        for _ in range(3):
            request = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={
                    "Authorization": f"Bearer {self.cloudflare_api_token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    result = json.loads(response.read().decode())
            except urllib.error.HTTPError as exc:
                details = exc.read().decode(errors="replace")
                raise RuntimeError(
                    f"Cloudflare API error ({exc.code}): {details}"
                ) from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(
                    f"Could not reach Cloudflare: {exc.reason}"
                ) from exc

            try:
                message = result["choices"][0]["message"]
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError(
                    f"Cloudflare returned an unexpected response: {result}"
                ) from exc

            content = message.get("content")
            if content:
                return str(content)

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                raise RuntimeError(
                    f"Cloudflare returned an unexpected response: {result}"
                )

            payload["messages"].append(message)
            for tool_call in tool_calls:
                function = tool_call.get("function") or {}
                name = function.get("name")
                handler = self.tool_handlers.get(name)
                if handler is None:
                    raise RuntimeError(f"Cloudflare requested an unknown tool: {name}")

                try:
                    args = self._parse_tool_arguments(
                        function.get("arguments", "{}")
                    )
                    tool_result = handler(**args)
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                    args = {}
                    tool_result = f"Tool error: {exc}"

                call_trace = {"name": name, "args": args, "result": tool_result}
                if "expression" in args:
                    call_trace["expression"] = str(args["expression"])
                self.last_tool_calls.append(call_trace)

                payload["messages"].append({
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "content": str(tool_result),
                })

        raise RuntimeError("Cloudflare requested too many tool calls.")

    @staticmethod
    def _requested_local_tool(contents: list[dict]) -> str | None:
        """Return an explicitly named local tool requested by the user."""
        user_text = ""
        for item in reversed(contents):
            if item.get("role") == "user":
                user_text = " ".join(
                    part.get("text", "")
                    for part in item.get("parts", [])
                    if isinstance(part, dict) and isinstance(part.get("text"), str)
                ).lower()
                break
        for declaration in TOOL_DECLARATIONS:
            name = declaration["name"]
            if name.lower() in user_text:
                return name
        return None

    @classmethod
    def _requires_local_tool(cls, contents: list[dict]) -> bool:
        """Require a local tool when the user explicitly asks for a filesystem action."""
        if cls._requested_local_tool(contents):
            return True
        user_text = ""
        for item in reversed(contents):
            if item.get("role") == "user":
                user_text = " ".join(
                    part.get("text", "")
                    for part in item.get("parts", [])
                    if isinstance(part, dict) and isinstance(part.get("text"), str)
                ).lower()
                break
        return any(
            term in user_text
            for term in (
                "append ",
                "write ",
                "read ",
                "create ",
                "overwrite ",
                "file",
                "directory",
                "folder",
            )
        )

    @staticmethod
    def _extract_openrouter_sources(message: dict) -> list[dict[str, str]]:
        annotations = message.get("annotations") or []
        return [
            {
                "title": str((annotation.get("url_citation") or {}).get("title") or annotation.get("title") or annotation.get("url", "Untitled")),
                "uri": str((annotation.get("url_citation") or {}).get("url") or annotation["url"]),
            }
            for annotation in annotations
            if isinstance(annotation, dict)
            and annotation.get("type") == "url_citation"
            and (annotation.get("url") or isinstance(annotation.get("url_citation"), dict) and annotation["url_citation"].get("url"))
        ]

    @staticmethod
    def _parse_textual_tool_call(content) -> tuple[str, dict] | None:
        """Parse a model's exact list-shaped textual tool call fallback."""
        if not isinstance(content, str):
            return None
        text = content.strip()
        if not text.startswith("["):
            return None
        try:
            import ast
            parsed = ast.literal_eval(text)
        except (SyntaxError, ValueError):
            return None

        calls = parsed
        if isinstance(calls, list) and len(calls) == 1 and isinstance(calls[0], list):
            calls = calls[0]
        if not isinstance(calls, list) or len(calls) != 1 or not isinstance(calls[0], dict):
            return None

        call = calls[0]
        name = call.get("name")
        args = call.get("parameters")
        if not isinstance(name, str) or not isinstance(args, dict):
            return None
        if name not in {declaration["name"] for declaration in TOOL_DECLARATIONS}:
            return None
        return name, args

    def _generate_openrouter(
        self,
        contents: list[dict],
        system_instruction: str | None,
    ) -> str:
        if not self.openrouter_api_key:
            raise RuntimeError("No OpenRouter fallback is configured.")

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

        tools = [
            {
                "type": "function",
                "function": {
                    "name": declaration["name"],
                    "description": declaration["description"],
                    "parameters": self._groq_parameters(declaration["parameters"]),
                },
            }
            for declaration in TOOL_DECLARATIONS
        ]
        if self.web_search:
            tools.insert(0, {"type": "openrouter:web_search"})
        payload = {
            "model": self.openrouter_model,
            "messages": messages,
            "max_tokens": 1024,
            "tools": tools,
        }
        requested_tool = self._requested_local_tool(contents)
        if requested_tool:
            payload["tool_choice"] = {
                "type": "function",
                "function": {"name": requested_tool},
            }
        elif self._requires_local_tool(contents):
            payload["tool_choice"] = "required"

        for _ in range(3):
            request = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=json.dumps(payload).encode(),
                headers={
                    "Authorization": f"Bearer {self.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    result = json.loads(response.read().decode())
            except urllib.error.HTTPError as exc:
                details = exc.read().decode(errors="replace")
                raise RuntimeError(f"OpenRouter API error ({exc.code}): {details}") from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(f"Could not reach OpenRouter: {exc.reason}") from exc

            try:
                message = result["choices"][0]["message"]
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError(f"OpenRouter returned an unexpected response: {result}") from exc

            content = message.get("content")
            if content:
                textual_tool = self._parse_textual_tool_call(content)
                if textual_tool is not None:
                    name, args = textual_tool
                    handler = self.tool_handlers.get(name)
                    if handler is None:
                        raise RuntimeError(f"OpenRouter requested an unknown tool: {name}")
                    try:
                        tool_result = handler(**args)
                    except (KeyError, TypeError, ValueError) as exc:
                        tool_result = f"Tool error: {exc}"
                    call_trace = {"name": name, "args": args, "result": tool_result}
                    if "expression" in args:
                        call_trace["expression"] = str(args["expression"])
                    self.last_tool_calls.append(call_trace)
                    return str(tool_result)
                self.last_grounding_sources = self._extract_openrouter_sources(message)
                return str(content)

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                raise RuntimeError(f"OpenRouter returned an unexpected response: {result}")

            payload["messages"].append(message)
            for tool_call in tool_calls:
                function = tool_call.get("function") or {}
                name = function.get("name")
                handler = self.tool_handlers.get(name)
                if handler is None:
                    raise RuntimeError(f"OpenRouter requested an unknown tool: {name}")

                try:
                    args = self._parse_tool_arguments(function.get("arguments", "{}"))
                    tool_result = handler(**args)
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                    args = {}
                    tool_result = f"Tool error: {exc}"

                call_trace = {"name": name, "args": args, "result": tool_result}
                if "expression" in args:
                    call_trace["expression"] = str(args["expression"])
                self.last_tool_calls.append(call_trace)

                payload["messages"].append({
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "content": str(tool_result),
                })

        raise RuntimeError("OpenRouter requested too many tool calls.")

    @staticmethod
    def _is_hard_provider_failure(error_text: str) -> bool:
        """Return true for failures where immediate retries are wasteful."""
        lowered = error_text.lower()
        return any(marker in lowered for marker in (
            "free-models-per-day",
            "daily limit",
            "quota exhausted",
            "internal server error",
        ))

    def _disable_provider(self, provider: str, error_text: str) -> None:
        if self._is_hard_provider_failure(error_text):
            self._disabled_providers.add(provider)

    def _provider_enabled(self, provider: str) -> bool:
        return provider not in self._disabled_providers

    def _generate(
        self,
        contents: list[dict],
        system_instruction: str | None,
    ) -> dict | str:
        try:
            return self._generate_gemini(contents, system_instruction)
        except RuntimeError as gemini_error:
            error_text = str(gemini_error)
            gemini_retryable = (
                any(
                    f"API error ({code})" in error_text
                    for code in (429, 500, 502, 503, 504)
                )
                or error_text.startswith("Could not reach Gemini:")
            )
            if not gemini_retryable:
                raise

            if self.web_search:
                if self.openrouter_api_key and self._provider_enabled("openrouter"):
                    try:
                        return self._generate_openrouter(contents, system_instruction)
                    except RuntimeError as openrouter_error:
                        self._disable_provider("openrouter", str(openrouter_error))
                        if self.groq_api_key and self._provider_enabled("groq"):
                            return self._generate_groq(contents, system_instruction)
                        raise openrouter_error

                if self.groq_api_key and self._provider_enabled("groq"):
                    return self._generate_groq(contents, system_instruction)

            if self.groq_api_key and self._provider_enabled("groq"):
                try:
                    return self._generate_groq(contents, system_instruction)
                except RuntimeError as groq_error:
                    self._disable_provider("groq", str(groq_error))
                    if self.openrouter_api_key and self._provider_enabled("openrouter"):
                        try:
                            return self._generate_openrouter(contents, system_instruction)
                        except RuntimeError as openrouter_error:
                            self._disable_provider("openrouter", str(openrouter_error))
                            if (
                                (not self.web_search or self._requires_local_tool(contents))
                                and self.cloudflare_api_token
                                and self.cloudflare_account_id
                                and self._provider_enabled("cloudflare")
                            ):
                                return self._generate_cloudflare(
                                    contents, system_instruction
                                )
                            raise openrouter_error
                    if (
                        (not self.web_search or self._requires_local_tool(contents))
                        and self.cloudflare_api_token
                        and self.cloudflare_account_id
                        and self._provider_enabled("cloudflare")
                    ):
                        return self._generate_cloudflare(contents, system_instruction)
                    raise groq_error

            if self.openrouter_api_key and self._provider_enabled("openrouter"):
                try:
                    return self._generate_openrouter(contents, system_instruction)
                except RuntimeError as openrouter_error:
                    self._disable_provider("openrouter", str(openrouter_error))
                    if (
                        not self.web_search
                        and self.cloudflare_api_token
                        and self.cloudflare_account_id
                        and self._provider_enabled("cloudflare")
                    ):
                        return self._generate_cloudflare(contents, system_instruction)
                    raise openrouter_error

            if (
                (not self.web_search or self._requires_local_tool(contents))
                and self.cloudflare_api_token
                and self.cloudflare_account_id
                and self._provider_enabled("cloudflare")
            ):
                try:
                    return self._generate_cloudflare(contents, system_instruction)
                except RuntimeError as cloudflare_error:
                    self._disable_provider("cloudflare", str(cloudflare_error))
                    raise cloudflare_error

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

            function_calls = [
                part["functionCall"]
                for part in parts
                if isinstance(part, dict) and "functionCall" in part
            ]
            if not function_calls:
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

            function_responses = []
            for function_call in function_calls:
                name = function_call.get("name")
                args = function_call.get("args", {}) or {}
                if not isinstance(args, dict):
                    raise RuntimeError(f"Gemini returned invalid arguments for tool: {name}")
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
                function_responses.append({
                    "functionResponse": {
                        "name": name,
                        "response": {"result": tool_result},
                    }
                })

            contents.extend([
                {"role": "model", "parts": parts},
                {"role": "user", "parts": function_responses},
            ])
            result = self._generate_gemini(contents, system_instruction)

        raise RuntimeError("Gemini requested too many tool calls.")
