"""Cloudflare Workers AI client for the minimal Nova agent."""

import json
import re
import os
import urllib.error
import urllib.request
from collections.abc import Callable

from gemini_agent.tools import GET_PROCESS_COMMAND_LINE_DECLARATION, GET_PROCESS_EXECUTABLE_DECLARATION, GET_PROCESS_STATUS_DECLARATION, LIST_PROCESSES_DECLARATION, RUN_COMMAND_DECLARATION, TOOL_DECLARATIONS, TOOL_HANDLERS


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
        self.tool_declarations = [*TOOL_DECLARATIONS, RUN_COMMAND_DECLARATION, LIST_PROCESSES_DECLARATION, GET_PROCESS_STATUS_DECLARATION, GET_PROCESS_COMMAND_LINE_DECLARATION, GET_PROCESS_EXECUTABLE_DECLARATION]
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

    _CLOUD_TOOL_NAMES = {
        "read_text_file": "read_file",
        "create_directory": "make_directory",
        "delete_directory": "remove_directory",
        "edit_text_file": "edit_file",
    }

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
        if "run_command" in user_text:
            return "run_command"
        if "list_processes" in user_text:
            return "list_processes"
        if "get_process_status" in user_text:
            return "get_process_status"
        if "process status" in user_text:
            return "get_process_status"
        if "get_process_command_line" in user_text:
            return "get_process_command_line"
        if "process command line" in user_text:
            return "get_process_command_line"
        if "get_process_executable" in user_text:
            return "get_process_executable"
        if "process executable" in user_text:
            return "get_process_executable"
        for declaration in TOOL_DECLARATIONS:
            name = declaration["name"]
            if name.lower() in user_text:
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
        declarations = self.tool_declarations
        if requested_tool:
            declarations = [
                d for d in self.tool_declarations if d["name"] == requested_tool
            ]

        tools = [{
            "type": "function",
            "function": {
                "name": self._CLOUD_TOOL_NAMES.get(d["name"], d["name"]),
                "description": d["description"],
                "parameters": self._schema(d["parameters"]),
            },
        } for d in declarations]

        payload = {
            "model": self.cloudflare_model,
            "messages": messages,
            "max_completion_tokens": 2048,
            "tools": tools,
        }
        if requested_tool:
            payload["tool_choice"] = {
                "type": "function",
                "function": {"name": self._CLOUD_TOOL_NAMES.get(requested_tool, requested_tool)},
            }
        elif self._requires_local_tool(contents):
            payload["tool_choice"] = "required"

        url = (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{self.cloudflare_account_id}/ai/v1/chat/completions"
        )

        for loop_index in range(3):
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

            tool_calls = message.get("tool_calls") or []
            native_tool_calls = bool(tool_calls)

            if not tool_calls:
                content = message.get("content")
                if isinstance(content, str):
                    lines = content.strip().splitlines()
                    if len(lines) >= 2 and lines[0].strip() in {
                        d["name"] for d in self.tool_declarations
                    }:
                        try:
                            parsed_args = json.loads("\n".join(lines[1:]))
                            if isinstance(parsed_args, dict):
                                local_name = lines[0].strip()
                                cloud_name = self._CLOUD_TOOL_NAMES.get(
                                    local_name, local_name
                                )
                                tool_calls = [{
                                    "id": "content-tool-call",
                                    "type": "function",
                                    "function": {
                                        "name": cloud_name,
                                        "arguments": parsed_args,
                                    },
                                }]
                        except (json.JSONDecodeError, TypeError):
                            pass

                    if not tool_calls:
                        tool_call_match = re.search(
                            r"<tool_call>\s*([a-zA-Z_][a-zA-Z0-9_]*)"
                            r"(.*?)</tool_call>",
                            content,
                            re.DOTALL,
                        )
                        if tool_call_match:
                            local_name = tool_call_match.group(1)
                            body = tool_call_match.group(2)
                            pairs = re.findall(
                                r"<arg_key>\s*([^<]+?)\s*</arg_key>"
                                r"\s*<arg_value>\s*(.*?)\s*</arg_value>",
                                body,
                                re.DOTALL,
                            )
                            if local_name in {d["name"] for d in TOOL_DECLARATIONS}:
                                arguments = {
                                    key.strip(): value.strip() for key, value in pairs
                                }
                                cloud_name = self._CLOUD_TOOL_NAMES.get(
                                    local_name, local_name
                                )
                                tool_calls = [{
                                    "id": "content-xml-tool-call",
                                    "type": "function",
                                    "function": {
                                        "name": cloud_name,
                                        "arguments": arguments,
                                    },
                                }]

            content = message.get("content")

            # For explicit hash_file requests, derive the path from the user
            # instruction when the model emits no usable tool call.
            if requested_tool == "hash_file" and not tool_calls and not content:
                user_text = ""
                for item in reversed(payload["messages"]):
                    if item.get("role") == "user":
                        user_text = item.get("content", "")
                        break
                match = re.search(
                    r"hash_file\s+.*?(?:of|for)\s+(.+?)(?:[.]\s*)?$|hash(?:\s+the)?\s+(?:SHA-?256\s+)?(?:hash\s+)?(?:of|for)\s+(.+?)(?:[.]\s*)?$",
                    str(user_text).strip(),
                    re.IGNORECASE,
                )
                if match:
                    path = (match.group(1) or match.group(2)).strip()
                    tool_calls = [{
                        "id": "requested-hash-file",
                        "type": "function",
                        "function": {
                            "name": "hash_file",
                            "arguments": json.dumps({"path": path}),
                        },
                    }]

            # Explicit path-existence requests must use the user's path.
            if requested_tool == "path_exists" and loop_index == 0:
                user_text = ""
                for item in reversed(payload["messages"]):
                    if item.get("role") == "user":
                        user_text = item.get("content", "")
                        break
                match = re.search(
                    r"path_exists\s+tool\s+to\s+check\s+whether\s+(.+?)\s+exists(?:[.]\s*)?$",
                    str(user_text).strip(),
                    re.IGNORECASE,
                )
                if not match:
                    match = re.search(
                        r"path_exists\s+.*?(?:of|for|path)\s+(.+?)(?:[.]\s*)?$",
                        str(user_text).strip(),
                        re.IGNORECASE,
                    )
                if match:
                    tool_calls = [{
                        "id": "requested-path-exists",
                        "type": "function",
                        "function": {
                            "name": "path_exists",
                            "arguments": json.dumps({"path": match.group(1).strip()}),
                        },
                    }]
                    native_tool_calls = False

            # For explicit get_directory_size requests, derive the path from
            # the user's instruction when the model emits no usable tool call.
            if requested_tool == "get_directory_size" and loop_index == 0 and not tool_calls:
                user_text = ""
                for item in reversed(payload["messages"]):
                    if item.get("role") == "user":
                        user_text = item.get("content", "")
                        break
                match = re.search(
                    r"(?:get_directory_size|directory\s+size).*?(?:of|for|directory)\s+(.+?)(?:[.]\s*)?$",
                    str(user_text).strip(),
                    re.IGNORECASE,
                )
                if match:
                    path = match.group(1).strip()
                    tool_calls = [{
                        "id": "requested-directory-size",
                        "type": "function",
                        "function": {
                            "name": "get_directory_size",
                            "arguments": json.dumps({"path": path}),
                        },
                    }]

            # Explicit line-count requests must use the user's path.
            if requested_tool == "count_file_lines" and loop_index == 0:
                user_text = ""
                for item in reversed(payload["messages"]):
                    if item.get("role") == "user":
                        user_text = item.get("content", "")
                        break
                match = re.search(
                    r"(?:count_file_lines|count(?:\s+the)?\s+lines).*?(?:of|in|for)\s+(.+?)(?:[.]\s*)?$",
                    str(user_text).strip(),
                    re.IGNORECASE,
                )
                if match:
                    tool_calls = [{
                        "id": "requested-count-file-lines",
                        "type": "function",
                        "function": {
                            "name": "count_file_lines",
                            "arguments": json.dumps({"path": match.group(1).strip()}),
                        },
                    }]
                    native_tool_calls = False

            # Explicit disk-usage requests must use the user's path.
            if requested_tool == "get_hostname" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-hostname",
                    "type": "function",
                    "function": {
                        "name": "get_hostname",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "get_system_info" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-system-info",
                    "type": "function",
                    "function": {
                        "name": "get_system_info",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "get_process_id" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-process-id",
                    "type": "function",
                    "function": {
                        "name": "get_process_id",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "get_current_working_directory" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-current-working-directory",
                    "type": "function",
                    "function": {
                        "name": "get_current_working_directory",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "get_python_executable" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-python-executable",
                    "type": "function",
                    "function": {
                        "name": "get_python_executable",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "get_cpu_count" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-cpu-count",
                    "type": "function",
                    "function": {
                        "name": "get_cpu_count",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "get_memory_usage" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-memory-usage",
                    "type": "function",
                    "function": {
                        "name": "get_memory_usage",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "get_temp_directory" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-temp-directory",
                    "type": "function",
                    "function": {
                        "name": "get_temp_directory",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "get_home_directory" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-home-directory",
                    "type": "function",
                    "function": {
                        "name": "get_home_directory",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "get_process_uptime" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-process-uptime",
                    "type": "function",
                    "function": {
                        "name": "get_process_uptime",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "get_process_thread_count" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-process-thread-count",
                    "type": "function",
                    "function": {
                        "name": "get_process_thread_count",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "get_user_id" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-user-id",
                    "type": "function",
                    "function": {
                        "name": "get_user_id",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "get_session_id" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-session-id",
                    "type": "function",
                    "function": {
                        "name": "get_session_id",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "get_process_group_id" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-process-group-id",
                    "type": "function",
                    "function": {
                        "name": "get_process_group_id",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "get_parent_process_id" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-parent-process-id",
                    "type": "function",
                    "function": {
                        "name": "get_parent_process_id",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "list_processes" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-list-processes",
                    "type": "function",
                    "function": {
                        "name": "list_processes",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False
            if requested_tool == "get_process_status" and loop_index == 0:
                user_text = ""
                for item in reversed(payload["messages"]):
                    if item.get("role") == "user":
                        user_text = item.get("content", "")
                        break
                match = re.search(
                    r"(?:pid|for\s+pid|for|of)\s+(\d+)",
                    str(user_text).strip(),
                    re.IGNORECASE,
                )
                if match:
                    tool_calls = [{
                        "id": "requested-process-status",
                        "type": "function",
                        "function": {
                            "name": "get_process_status",
                            "arguments": json.dumps({"pid": match.group(1)}),
                        },
                    }]
                    native_tool_calls = False


            if requested_tool == "get_process_executable" and loop_index == 0:
                user_text = ""
                for item in reversed(payload["messages"]):
                    if item.get("role") == "user":
                        user_text = item.get("content", "")
                        break
                match = re.search(
                    r"(?:pid|for\s+pid|for|of)\s+(\d+)",
                    str(user_text).strip(),
                    re.IGNORECASE,
                )
                if match:
                    tool_calls = [{
                        "id": "requested-process-executable",
                        "type": "function",
                        "function": {
                            "name": "get_process_executable",
                            "arguments": json.dumps({"pid": match.group(1)}),
                        },
                    }]
                    native_tool_calls = False

            if requested_tool == "get_process_command_line" and loop_index == 0:
                user_text = ""
                for item in reversed(payload["messages"]):
                    if item.get("role") == "user":
                        user_text = item.get("content", "")
                        break
                match = re.search(
                    r"(?:pid|for\s+pid|for|of)\s+(\d+)",
                    str(user_text).strip(),
                    re.IGNORECASE,
                )
                if match:
                    tool_calls = [{
                        "id": "requested-process-command-line",
                        "type": "function",
                        "function": {
                            "name": "get_process_command_line",
                            "arguments": json.dumps({"pid": match.group(1)}),
                        },
                    }]
                    native_tool_calls = False

            if requested_tool == "run_command" and loop_index == 0:
                user_text = ""
                for item in reversed(payload["messages"]):
                    if item.get("role") == "user":
                        user_text = item.get("content", "")
                        break
                match = re.search(r"`([^\`]+)`", str(user_text))
                if match:
                    tool_calls = [{
                        "id": "requested-run-command",
                        "type": "function",
                        "function": {
                            "name": "run_command",
                            "arguments": json.dumps({"command": match.group(1).strip()}),
                        },
                    }]
                    native_tool_calls = False

            if requested_tool == "get_umask" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-umask",
                    "type": "function",
                    "function": {
                        "name": "get_umask",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "get_disk_usage" and loop_index == 0:
                user_text = ""
                for item in reversed(payload["messages"]):
                    if item.get("role") == "user":
                        user_text = item.get("content", "")
                        break
                match = re.search(
                    r"(?:get_disk_usage|disk\s+usage|disk\s+space).*?(?:of|for|path|on)\s+(.+?)(?:[.]\s*)?$",
                    str(user_text).strip(),
                    re.IGNORECASE,
                )
                path = match.group(1).strip() if match else "."
                tool_calls = [{
                    "id": "requested-disk-usage",
                    "type": "function",
                    "function": {
                        "name": "get_disk_usage",
                        "arguments": json.dumps({"path": path}),
                    },
                }]
                native_tool_calls = False

            # Explicit directory-size requests must use the user's path.
            if requested_tool == "get_directory_entry_count" and loop_index == 0:
                user_text = ""
                for item in reversed(payload["messages"]):
                    if item.get("role") == "user":
                        user_text = item.get("content", "")
                        break
                match = re.search(
                    r"(?:get_directory_entry_count|directorys+entrys+count|counts+entries).*?(?:of|for|directory)s+(.+?)(?:[.]s*)?$",
                    str(user_text).strip(),
                    re.IGNORECASE,
                )
                if match:
                    tool_calls = [{
                        "id": "requested-directory-entry-count",
                        "type": "function",
                        "function": {
                            "name": "get_directory_entry_count",
                            "arguments": json.dumps({"path": match.group(1).strip()}),
                        },
                    }]
                    native_tool_calls = False

            if requested_tool == "get_directory_size" and loop_index == 0:
                user_text = ""
                for item in reversed(payload["messages"]):
                    if item.get("role") == "user":
                        user_text = item.get("content", "")
                        break
                match = re.search(
                    r"get_directory_size\s+.*?(?:of|for|directory)\s+(.+?)(?:[.]\s*)?$",
                    str(user_text).strip(),
                    re.IGNORECASE,
                )
                if match:
                    tool_calls = [{
                        "id": "requested-directory-size",
                        "type": "function",
                        "function": {
                            "name": "get_directory_size",
                            "arguments": json.dumps({"path": match.group(1).strip()}),
                        },
                    }]
                    native_tool_calls = False

            # Explicit modification-time requests must use the user's path.
            if requested_tool == "get_file_access_time" and loop_index == 0:
                user_text = ""
                for item in reversed(payload["messages"]):
                    if item.get("role") == "user":
                        user_text = item.get("content", "")
                        break
                match = re.search(
                    r"(?:get_file_access_time|accesss+time).*?(?:of|for|path)s+(.+?)(?:[.]s*)?$",
                    str(user_text).strip(),
                    re.IGNORECASE,
                )
                if match:
                    tool_calls = [{
                        "id": "requested-file-access-time",
                        "type": "function",
                        "function": {
                            "name": "get_file_access_time",
                            "arguments": json.dumps({"path": match.group(1).strip()}),
                        },
                    }]
                    native_tool_calls = False

            if requested_tool == "get_file_modified_time" and loop_index == 0:
                user_text = ""
                for item in reversed(payload["messages"]):
                    if item.get("role") == "user":
                        user_text = item.get("content", "")
                        break
                match = re.search(
                    r"(?:get_file_modified_time|modified\s+time|modification\s+time).*?(?:of|for|path)\s+(.+?)(?:[.]\s*)?$",
                    str(user_text).strip(),
                    re.IGNORECASE,
                )
                if match:
                    tool_calls = [{
                        "id": "requested-file-modified-time",
                        "type": "function",
                        "function": {
                            "name": "get_file_modified_time",
                            "arguments": json.dumps({"path": match.group(1).strip()}),
                        },
                    }]
                    native_tool_calls = False

            # Explicit file-name requests must use the user's path.
            if requested_tool == "get_file_name" and loop_index == 0:
                user_text = ""
                for item in reversed(payload["messages"]):
                    if item.get("role") == "user":
                        user_text = item.get("content", "")
                        break
                match = re.search(
                    r"(?:get_file_name|file\s+name|base\s+name).*?(?:of|for|path)\s+(.+?)(?:[.]\s*)?$",
                    str(user_text).strip(),
                    re.IGNORECASE,
                )
                if match:
                    tool_calls = [{"id":"requested-file-name","type":"function","function":{"name":"get_file_name","arguments":json.dumps({"path":match.group(1).strip()})}}]
                    native_tool_calls = False

            # Explicit file-stem requests must use the user's path.
            if requested_tool == "get_file_stem" and loop_index == 0:
                user_text = ""
                for item in reversed(payload["messages"]):
                    if item.get("role") == "user":
                        user_text = item.get("content", "")
                        break
                match = re.search(
                    r"(?:get_file_stem|file\s+stem|name\s+without\s+(?:the\s+)?extension).*?(?:of|for|path)\s+(.+?)(?:[.]\s*)?$",
                    str(user_text).strip(),
                    re.IGNORECASE,
                )
                if match:
                    tool_calls = [{"id":"requested-file-stem","type":"function","function":{"name":"get_file_stem","arguments":json.dumps({"path":match.group(1).strip()})}}]
                    native_tool_calls = False

            # Explicit file-parent requests must use the user's path.
            if requested_tool == "get_file_parent" and loop_index == 0:
                user_text = ""
                for item in reversed(payload["messages"]):
                    if item.get("role") == "user":
                        user_text = item.get("content", "")
                        break
                match = re.search(
                    r"(?:get_file_parent|parent\s+path|parent\s+directory).*?(?:\bof\b|\bfor\b|\bpath\b)\s+(.+?)(?:[.]\s*)?$",
                    str(user_text).strip(),
                    re.IGNORECASE,
                )
                if match:
                    tool_calls = [{
                        "id": "requested-file-parent",
                        "type": "function",
                        "function": {
                            "name": "get_file_parent",
                            "arguments": json.dumps({"path": match.group(1).strip()}),
                        },
                    }]
                    native_tool_calls = False

            # Explicit permission requests must use the user's path.
            if requested_tool == "get_file_permissions" and loop_index == 0:
                user_text = ""
                for item in reversed(payload["messages"]):
                    if item.get("role") == "user":
                        user_text = item.get("content", "")
                        break
                match = re.search(
                    r"(?:get_file_permissions|file\s+permissions|permissions|permission\s+mode).*?(?:of|for|path)\s+(.+?)(?:[.]\s*)?$",
                    str(user_text).strip(),
                    re.IGNORECASE,
                )
                if match:
                    tool_calls = [{
                        "id": "requested-file-permissions",
                        "type": "function",
                        "function": {
                            "name": "get_file_permissions",
                            "arguments": json.dumps({"path": match.group(1).strip()}),
                        },
                    }]
                    native_tool_calls = False

            # Explicit file-extension requests must use the user's path.
            if requested_tool == "get_file_extension" and loop_index == 0:
                user_text = ""
                for item in reversed(payload["messages"]):
                    if item.get("role") == "user":
                        user_text = item.get("content", "")
                        break
                match = re.search(
                    r"(?:get_file_extension|file\s+extension|extension).*?(?:of|for|path)\s+(.+?)(?:[.]\s*)?$",
                    str(user_text).strip(),
                    re.IGNORECASE,
                )
                if match:
                    tool_calls = [{
                        "id": "requested-file-extension",
                        "type": "function",
                        "function": {
                            "name": "get_file_extension",
                            "arguments": json.dumps({"path": match.group(1).strip()}),
                        },
                    }]
                    native_tool_calls = False

            # For explicit copy_directory requests, derive source and destination
            # from the user's instruction instead of trusting model-generated arguments.
            if requested_tool == "copy_directory" and (native_tool_calls or (not tool_calls and not content)):
                user_text = ""
                for item in reversed(payload["messages"]):
                    if item.get("role") == "user":
                        user_text = item.get("content", "")
                        break
                match = re.search(
                    r"copy\s+(.+?)\s+to\s+(.+?)(?:[.]\s*)?$",
                    str(user_text).strip(),
                    re.IGNORECASE,
                )
                if match:
                    tool_calls = [{
                        "id": "requested-copy-directory",
                        "type": "function",
                        "function": {
                            "name": "copy_directory",
                            "arguments": json.dumps({
                                "path": match.group(1).strip(),
                                "destination": match.group(2).strip(),
                            }),
                        },
                    }]
                    native_tool_calls = False

            if tool_calls:
                if native_tool_calls:
                    normalized_message = dict(message)
                    normalized_tool_calls = []
                    for tool_call in tool_calls:
                        normalized_tool_call = dict(tool_call)
                        function = dict(normalized_tool_call.get("function") or {})
                        arguments = function.get("arguments", "{}")
                        if isinstance(arguments, dict):
                            function["arguments"] = json.dumps(arguments)
                        normalized_tool_call["function"] = function
                        normalized_tool_calls.append(normalized_tool_call)
                    normalized_message["tool_calls"] = normalized_tool_calls
                    payload["messages"].append(normalized_message)
                else:
                    payload["messages"].append({
                        "role": "assistant",
                        "tool_calls": tool_calls,
                    })

                for tool_call in tool_calls:
                    function = tool_call.get("function") or {}
                    name = function.get("name")
                    local_name = next(
                        (tool_name for tool_name, cloud_name in self._CLOUD_TOOL_NAMES.items() if cloud_name == name),
                        name,
                    )
                    handler = self.tool_handlers.get(local_name)
                    if handler is None:
                        raise RuntimeError(f"Cloudflare requested an unknown tool: {name}")

                    try:
                        args = self._parse_tool_arguments(function.get("arguments", "{}"))
                        tool_result = handler(**args)
                    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                        args = {}
                        tool_result = f"Tool error: {exc}"

                    trace = {"name": local_name, "args": args, "result": tool_result}
                    if "expression" in args:
                        trace["expression"] = str(args["expression"])
                    self.last_tool_calls.append(trace)

                    payload["messages"].append({
                        "role": "tool",
                        "tool_call_id": tool_call.get("id", ""),
                        "content": str(tool_result),
                    })

                # Deterministic explicit filesystem requests do not need a second
                # Cloudflare round-trip. Return the local tool result directly.
                if requested_tool in {"list_processes", "run_command", "path_exists", "get_file_access_time", "get_file_modified_time", "get_file_extension", "get_file_name", "get_file_stem", "get_file_permissions", "get_directory_entry_count", "get_directory_size", "count_file_lines", "get_disk_usage", "get_hostname", "get_system_info", "get_cpu_count", "get_process_id", "get_current_working_directory", "get_python_executable", "get_memory_usage", "get_temp_directory", "get_home_directory", "get_process_uptime", "get_process_thread_count", "get_parent_process_id", "get_process_group_id", "get_session_id", "get_user_id", "get_umask", "get_process_status", "get_process_command_line", "get_process_executable"} and loop_index == 0:
                    return str(tool_result)

                # Tool execution is Nova's responsibility. After executing the
                # requested tool(s), ask Cloudflare only to synthesize the result,
                # preventing the model from repeatedly requesting the same tool.
                payload.pop("tools", None)
                payload.pop("tool_choice", None)
                continue

            elif not content:
                raise RuntimeError(
                    f"Cloudflare returned an unexpected response: {result}"
                )
            return str(content)

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
