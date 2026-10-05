"""Cloudflare Workers AI client for the minimal Nova agent."""

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable

from gemini_agent.tools import TOOL_DECLARATIONS, TOOL_HANDLERS


class GeminiClient:
    """Compatibility name for Nova's single Cloudflare provider client."""

    def __init__(
        self,
        model: str = "gemini-3.5-flash-lite",
        fallback_model: str = "gemini-3.5-flash",
        tool_handlers: dict[str, Callable[..., str]] | None = None,
    ) -> None:
        del model, fallback_model
        self.cloudflare_api_token = os.environ.get("CLOUDFLARE_API_TOKEN")
        self.cloudflare_account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        self.cloudflare_model = os.environ.get(
            "CLOUDFLARE_MODEL", "@cf/zai-org/glm-4.7-flash"
        )
        if not self.cloudflare_api_token or not self.cloudflare_account_id:
            raise RuntimeError(
                "Configure CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID before starting the agent."
            )
        self.tool_handlers = {**TOOL_HANDLERS, **(tool_handlers or {})}
        self.last_tool_calls: list[dict] = []
        self.last_grounding_sources: list[dict[str, str]] = []

    @staticmethod
    def _schema(parameters: dict) -> dict:
        converted = json.loads(json.dumps(parameters))

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
        if arguments in (None, ""):
            return {}
        if isinstance(arguments, dict):
            return arguments
        parsed = json.loads(arguments)
        if not isinstance(parsed, dict):
            raise ValueError("Tool arguments must be a JSON object.")
        return parsed

    _TOOL_ALIASES = {"read_text_file": "read_file"}

    @classmethod
    def _requested_local_tool(cls, contents: list[dict]) -> str | None:
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
        for alias, name in cls._TOOL_ALIASES.items():
            if alias in user_text:
                return name
        return None

    @classmethod
    def _requires_local_tool(cls, contents: list[dict]) -> bool:
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
                "append ", "write ", "read ", "create ", "overwrite ",
                "file", "directory", "folder",
            )
        )

    def _generate_cloudflare(
        self,
        contents: list[dict],
        system_instruction: str | None,
    ) -> str:
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
                d for d in TOOL_DECLARATIONS if d["name"] == requested_tool
            ]

        tools = [{
            "type": "function",
            "function": {
                "name": d["name"],
                "description": d["description"],
                "parameters": self._schema(d["parameters"]),
            },
        } for d in declarations]

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
                    args = self._parse_tool_arguments(function.get("arguments", "{}"))
                    tool_result = handler(**args)
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                    args = {}
                    tool_result = f"Tool error: {exc}"

                trace = {"name": name, "args": args, "result": tool_result}
                if "expression" in args:
                    trace["expression"] = str(args["expression"])
                self.last_tool_calls.append(trace)

                payload["messages"].append({
                    "role": "tool",
                    "tool_call_id": tool_call.get("id", ""),
                    "content": str(tool_result),
                })

            # Tool execution is Nova's responsibility. After executing the
            # requested tool(s), ask Cloudflare only to synthesize the result,
            # preventing the model from repeatedly requesting the same tool.
            payload.pop("tools", None)
            payload.pop("tool_choice", None)

        raise RuntimeError("Cloudflare requested too many tool calls.")

    def ask(
        self,
        prompt: str,
        history: list[dict] | None = None,
        system_instruction: str | None = None,
    ) -> str:
        contents = list(history or []) + [
            {"role": "user", "parts": [{"text": prompt}]}
        ]
        self.last_tool_calls = []
        self.last_grounding_sources = []
        return self._generate_cloudflare(contents, system_instruction)
