"""Cloudflare Workers AI client for the minimal Nova agent."""

import json
import re
import os
from pathlib import Path
import urllib.error
import urllib.request
from collections.abc import Callable

from gemini_agent.tools import FIND_EXECUTABLE_DECLARATION, DIAGNOSE_COMMAND_FAILURE_DECLARATION, VERIFY_COMMAND_RESULT_DECLARATION, RETRY_COMMAND_DECLARATION, RECOVER_COMMAND_DECLARATION, RUN_ROOT_COMMAND_DECLARATION, GET_NETWORK_ADDRESSES_DECLARATION, GET_PROCESS_COMMAND_LINE_DECLARATION, GET_PROCESS_CPU_TIME_DECLARATION, GET_PROCESS_MEMORY_USAGE_DECLARATION, GET_PROCESS_NICE_DECLARATION, GET_PROCESS_EXECUTABLE_DECLARATION, GET_PROCESS_PARENT_NAME_DECLARATION, GET_PROCESS_START_TIME_DECLARATION, GET_PROCESS_STATUS_DECLARATION, GET_PROCESS_WORKING_DIRECTORY_DECLARATION, GET_SYSTEM_BATTERY_STATUS_DECLARATION, GET_WIFI_STATUS_DECLARATION, GET_BLUETOOTH_STATUS_DECLARATION, GET_AIRPLANE_MODE_DECLARATION, GET_SYSTEM_MEMORY_USAGE_DECLARATION, GET_SYSTEM_SCREEN_STATE_DECLARATION, GET_SYSTEM_SCREEN_BRIGHTNESS_DECLARATION, GET_SYSTEM_SCREEN_ORIENTATION_DECLARATION, GET_SYSTEM_SCREEN_RESOLUTION_DECLARATION, GET_SYSTEM_SCREEN_DENSITY_DECLARATION, GET_MEDIA_VOLUME_DECLARATION, GET_SYSTEM_SCREEN_REFRESH_RATE_DECLARATION, GET_SYSTEM_SCREEN_TIMEOUT_DECLARATION, GET_SYSTEM_BOOT_TIME_DECLARATION, GET_SYSTEM_CPU_USAGE_DECLARATION, GET_SYSTEM_MEMORY_USAGE_DECLARATION, GET_SYSTEM_SWAP_USAGE_DECLARATION, LIST_PROCESSES_DECLARATION, RUN_COMMAND_DECLARATION, TOOL_DECLARATIONS, TOOL_HANDLERS


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
        declarations = [*TOOL_DECLARATIONS, FIND_EXECUTABLE_DECLARATION, DIAGNOSE_COMMAND_FAILURE_DECLARATION, VERIFY_COMMAND_RESULT_DECLARATION, RETRY_COMMAND_DECLARATION, RUN_ROOT_COMMAND_DECLARATION, RUN_COMMAND_DECLARATION, LIST_PROCESSES_DECLARATION, GET_PROCESS_STATUS_DECLARATION, GET_PROCESS_COMMAND_LINE_DECLARATION, GET_PROCESS_EXECUTABLE_DECLARATION, GET_PROCESS_WORKING_DIRECTORY_DECLARATION, GET_PROCESS_PARENT_NAME_DECLARATION, GET_PROCESS_START_TIME_DECLARATION, GET_PROCESS_CPU_TIME_DECLARATION, GET_PROCESS_MEMORY_USAGE_DECLARATION, GET_PROCESS_NICE_DECLARATION, GET_NETWORK_ADDRESSES_DECLARATION, GET_SYSTEM_BATTERY_STATUS_DECLARATION, GET_SYSTEM_SCREEN_STATE_DECLARATION, GET_SYSTEM_SCREEN_TIMEOUT_DECLARATION, GET_SYSTEM_SCREEN_ORIENTATION_DECLARATION, GET_SYSTEM_SCREEN_RESOLUTION_DECLARATION, GET_SYSTEM_SCREEN_DENSITY_DECLARATION, GET_MEDIA_VOLUME_DECLARATION, GET_SYSTEM_SCREEN_REFRESH_RATE_DECLARATION, GET_SYSTEM_BOOT_TIME_DECLARATION, GET_SYSTEM_SWAP_USAGE_DECLARATION, GET_AIRPLANE_MODE_DECLARATION]
        self.tool_declarations = []
        seen = set()
        for declaration in declarations:
            name = declaration["name"]
            if name not in seen:
                self.tool_declarations.append(declaration)
                seen.add(name)

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
        if "self-test" in user_text or "self test" in user_text:
            return "self_test"
        if any(phrase in user_text for phrase in ("plan a capability extension", "plan an extension", "extend yourself", "add this capability", "how would you add this capability")):
            return "plan_capability_extension"
        if "apply capability extension" in user_text or "apply the capability extension" in user_text or "apply the extension" in user_text:
            return "apply_capability_extension"
        if any(phrase in user_text for phrase in ("do i have a capability", "do you have a capability", "is there a tool", "can you do this", "can you do that", "do you support this")):
            return "assess_capability_gap"
        if "capability inventory" in user_text or "capabilities" in user_text or "what tools" in user_text:
            return "capability_inventory"
        if "assess_capability_gap" in user_text:
            return "assess_capability_gap"
        if "find_executable" in user_text:
            return "find_executable"
        if "diagnose_command_failure" in user_text:
            return "diagnose_command_failure"
        if "verify_command_result" in user_text:
            return "verify_command_result"
        if "retry_command" in user_text:
            return "retry_command"
        if "recover_command" in user_text:
            return "recover_command"
        if "run_command" in user_text:
            return "run_command"
        if "run_root_command" in user_text:
            return "run_root_command"
        if "list_processes" in user_text:
            return "list_processes"
        if "get_network_addresses" in user_text:
            return "get_network_addresses"
        if "get_system_battery_status" in user_text:
            return "get_system_battery_status"
        if "get_wifi_status" in user_text:
            return "get_wifi_status"
        if "get_bluetooth_status" in user_text:
            return "get_bluetooth_status"
        if "get_airplane_mode" in user_text:
            return "get_airplane_mode"
        if "get_system_memory_usage" in user_text:
            return "get_system_memory_usage"
        if "get_screen_state" in user_text:
            return "get_screen_state"
        if "get_screen_brightness_mode" in user_text:
            return "get_screen_brightness_mode"
        if "get_screen_orientation" in user_text:
            return "get_screen_orientation"
        if "get_screen_resolution" in user_text:
            return "get_screen_resolution"
        if "get_screen_density" in user_text:
            return "get_screen_density"
        if "get_media_volume" in user_text:
            return "get_media_volume"
        if "get_screen_refresh_rate" in user_text:
            return "get_screen_refresh_rate"
        if "get_screen_brightness" in user_text:
            return "get_screen_brightness"
        if "get_screen_timeout" in user_text:
            return "get_screen_timeout"
        if "get_system_swap_usage" in user_text:
            return "get_system_swap_usage"
        if "get_system_boot_time" in user_text:
            return "get_system_boot_time"
        if "get_network_interfaces" in user_text:
            return "get_network_interfaces"
        if "network interfaces" in user_text or "network interface" in user_text:
            return "get_network_interfaces"
        if "network addresses" in user_text or "ip addresses" in user_text or "local ip" in user_text:
            return "get_network_addresses"
        if "get_process_cpu_time" in user_text:
            return "get_process_cpu_time"
        if "get_process_memory_usage" in user_text:
            return "get_process_memory_usage"
        if "get_process_nice" in user_text:
            return "get_process_nice"
        if "process nice value" in user_text or "nice value of process" in user_text:
            return "get_process_nice"
        if "process memory usage" in user_text or "memory usage of process" in user_text:
            return "get_process_memory_usage"
        if "process cpu time" in user_text or "cpu time of process" in user_text:
            return "get_process_cpu_time"
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
        if "get_process_working_directory" in user_text:
            return "get_process_working_directory"
        if "process working directory" in user_text:
            return "get_process_working_directory"
        if "get_process_parent_name" in user_text:
            return "get_process_parent_name"
        if "process parent name" in user_text or "parent process name" in user_text:
            return "get_process_parent_name"
        if "get_process_start_time" in user_text:
            return "get_process_start_time"
        if "process start time" in user_text or "start time of process" in user_text:
            return "get_process_start_time"
        for declaration in TOOL_DECLARATIONS:
            name = declaration["name"]
            if name.lower() in user_text:
                return name
        return None

    def _relevant_tool_declarations(self, contents: list[dict]) -> list[dict]:
        """Narrow the model's tool set when the user's intent is unambiguous."""
        user_text = ""
        for item in reversed(contents):
            if item.get("role") == "user":
                user_text = " ".join(
                    part.get("text", "")
                    for part in item.get("parts", [])
                    if isinstance(part, dict) and isinstance(part.get("text"), str)
                ).lower()
                break

        groups = {
            "calculator": ("calculate", "arithmetic", "multiply", "divide", "addition", "subtract"),
            "current_datetime": ("current date", "current time", "date and time", "what time is it"),
            "battery": ("battery", "power level", "charging", "battery health"),
            "network": ("network", "wifi", "wi-fi", "bluetooth", "airplane", "ip address", "network interface"),
            "screen": ("screen", "display", "brightness", "orientation", "resolution", "refresh rate", "screen timeout"),
            "process": ("process", "pid", "cpu time", "memory usage of process", "nice value"),
            "filesystem": ("file", "directory", "folder", "filesystem", "path", "read", "write", "append", "copy", "move", "delete"),
            "system": ("system information", "system info", "uptime", "boot time", "cpu usage", "memory usage", "swap", "hostname", "load average"),
            "recovery": ("recover", "retry", "diagnose", "failure", "failed command", "find executable", "executable"),
            "root": ("root", "su", "privileged", "dumpsys"),
        }

        selected_groups = {
            group for group, terms in groups.items()
            if any(term in user_text for term in terms)
        }
        if not selected_groups:
            return self.tool_declarations

        selected_names: set[str] = set()
        for declaration in self.tool_declarations:
            name = declaration["name"]
            if (
                (selected_groups & {"filesystem"} and name in {
                    "path_exists", "create_directory", "delete_directory", "get_file_info",
                    "get_file_access_time", "get_file_modified_time", "get_file_extension",
                    "get_file_name", "get_file_stem", "get_file_permissions", "get_file_parent",
                    "list_directory_recursive", "move_directory", "copy_directory", "hash_file",
                    "count_file_lines", "get_directory_entry_count", "get_disk_usage",
                    "get_directory_size", "list_directory", "read_text_file", "search_text",
                    "write_text_file", "edit_text_file", "append_text_file", "copy_file",
                    "move_file", "delete_file", "find_files",
                })
                or (selected_groups & {"process"} and name.startswith("get_process_"))
                or (selected_groups & {"network"} and name in {
                    "get_network_interfaces", "get_network_addresses", "get_wifi_status",
                    "get_bluetooth_status", "get_airplane_mode", "get_hostname",
                })
                or (selected_groups & {"screen"} and (
                    name.startswith("get_screen_") or name in {"get_media_volume", "get_system_screen_state"}
                ))
                or (selected_groups & {"battery"} and name == "get_system_battery_status")
                or (selected_groups & {"system"} and (
                    name.startswith("get_system_") or name in {"get_cpu_count", "get_load_average", "get_hostname"}
                ))
                or (selected_groups & {"recovery"} and name in {
                    "find_executable", "diagnose_command_failure", "verify_command_result",
                    "retry_command", "recover_command",
                })
                or (selected_groups & {"root"} and name in {"run_root_command", "run_command"})
                or (selected_groups & {"calculator"} and name == "calculator")
                or (selected_groups & {"current_datetime"} and name == "current_datetime")
            ):
                selected_names.add(name)

        selected = [d for d in self.tool_declarations if d["name"] in selected_names]
        return selected or cls.tool_declarations

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

    def _extension_inspection_context(self, request: str) -> str:
        """Inspect the local repository before a self-extension model call."""
        root = Path(os.environ.get("NOVA_FILES_ROOT", os.getcwd())).expanduser().resolve()
        python_files = []
        for base in (root / "gemini_agent", root / "tests"):
            if base.is_dir():
                python_files.extend(
                    path.relative_to(root).as_posix()
                    for path in base.rglob("*.py")
                    if path.is_file() and not path.is_symlink()
                )
        context = [
            f"Requested missing capability: {request}",
            "Repository inspection was performed locally before this model call.",
            "Existing Python targets under gemini_agent/ and tests/:",
            ", ".join(sorted(python_files)),
        ]
        source_path = root / "gemini_agent" / "tools.py"
        if source_path.is_file() and not source_path.is_symlink():
            source = source_path.read_text(encoding="utf-8")
            patterns = (
                "def assess_capability_gap",
                "def plan_capability_extension",
                "def apply_capability_extension",
                '"name": "assess_capability_gap"',
                '"name": "plan_capability_extension"',
                '"name": "apply_capability_extension"',
                '"apply_capability_extension": apply_capability_extension',
            )
            excerpts = []
            lines = source.splitlines()
            for pattern in patterns:
                for index, line in enumerate(lines):
                    if pattern in line:
                        start = max(0, index - 4)
                        end = min(len(lines), index + 9)
                        excerpt = "\\n".join(
                            f"{number + 1}: {lines[number]}"
                            for number in range(start, end)
                        )
                        if excerpt not in excerpts:
                            excerpts.append(excerpt)
                        break
            if excerpts:
                context.append("Relevant gemini_agent/tools.py excerpts:")
                context.extend(excerpts)
        context.append(
            "Use only an exact existing source fragment in apply_capability_extension. "
            "Do not invent a path or claim an implementation exists unless the inspected source supports it."
        )
        return "\\n".join(context)

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
        if requested_tool == "apply_capability_extension":
            request_text = next(
                item.get("content", "")
                for item in reversed(messages)
                if item.get("role") == "user"
            )
            inspection = self._extension_inspection_context(request_text)
            extension_system = (
                inspection
                + "\nThe only permitted action is to call apply_capability_extension. "
                + "Use the inspected repository facts to choose an existing Python file and "
                + "copy old_text exactly from the inspected source. Never invent a path or "
                + "source fragment. Call the function directly; do not emit prose or XML."
            )
            declarations = [
                d for d in self.tool_declarations
                if d["name"] == "apply_capability_extension"
            ]
            tools = [{
                "type": "function",
                "function": {
                    "name": "apply_capability_extension",
                    "description": d["description"],
                    "parameters": self._schema(d["parameters"]),
                },
            } for d in declarations]
            extension_payload = {
                "model": self.cloudflare_model,
                "messages": [
                    {"role": "system", "content": extension_system},
                    {"role": "user", "content": request_text},
                ],
                "max_completion_tokens": 2048,
                "tools": tools,
                "tool_choice": {
                    "type": "function",
                    "function": {"name": "apply_capability_extension"},
                },
            }
            url = (
                "https://api.cloudflare.com/client/v4/accounts/"
                f"{self.cloudflare_account_id}/ai/v1/chat/completions"
            )
            last_failure = "no response received"
            for loop_index in range(3):
                request = urllib.request.Request(
                    url,
                    data=json.dumps(extension_payload).encode(),
                    headers={
                        "Authorization": f"Bearer {self.cloudflare_api_token}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(request, timeout=180) as response:
                        result = json.loads(response.read().decode())
                except urllib.error.HTTPError as exc:
                    details = exc.read().decode(errors="replace")
                    raise RuntimeError(
                        f"Cloudflare API error ({exc.code}): {details}"
                    ) from exc
                except (TimeoutError, ConnectionAbortedError) as exc:
                    raise RuntimeError(
                        "Cloudflare request aborted or timed out while waiting for the model response."
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
                if not tool_calls:
                    last_failure = (
                        "model returned no native tool call; "
                        f"message keys={sorted(message.keys())}; "
                        f"content={str(message.get('content') or '')[:200]!r}"
                    )
                    extension_payload["messages"].append({
                        "role": "assistant",
                        "content": message.get("content") or "",
                    })
                    extension_payload["messages"].append({
                        "role": "user",
                        "content": "Call apply_capability_extension directly. Do not return prose or XML.",
                    })
                    continue

                tool_call = tool_calls[0]
                function = tool_call.get("function") or {}
                if function.get("name") != "apply_capability_extension":
                    last_failure = f"model called unexpected tool: {function.get('name')!r}"
                    extension_payload["messages"].append({
                        "role": "assistant",
                        "tool_calls": tool_calls,
                    })
                    extension_payload["messages"].append({
                        "role": "tool",
                        "tool_call_id": tool_call.get("id", ""),
                        "content": last_failure,
                    })
                    continue

                try:
                    args = self._parse_tool_arguments(function.get("arguments", "{}"))
                    tool_result = self.tool_handlers["apply_capability_extension"](**args)
                except Exception as exc:
                    args = {}
                    tool_result = f"Tool error: {exc}"

                self.last_tool_calls.append({
                    "name": "apply_capability_extension",
                    "arguments": args,
                    "result": str(tool_result),
                })

                if (
                    str(tool_result).startswith("Extension not applied:")
                    or str(tool_result).startswith("Tool error:")
                ):
                    last_failure = str(tool_result)
                    extension_payload["messages"].append({
                        "role": "assistant",
                        "tool_calls": tool_calls,
                    })
                    extension_payload["messages"].append({
                        "role": "tool",
                        "tool_call_id": tool_call.get("id", ""),
                        "content": str(tool_result),
                    })
                    extension_payload["messages"].append({
                        "role": "user",
                        "content": (
                            "The previous extension attempt failed. Inspect the supplied repository "
                            "context again and call apply_capability_extension with a corrected "
                            "existing path and exact old_text."
                        ),
                    })
                    continue
                return str(tool_result)

            return (
                "Extension not applied: no valid extension proposal was produced after 3 attempts. "
                f"Last model failure: {last_failure}"
            )
        declarations = self._relevant_tool_declarations(contents)
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
        if requested_tool == "apply_capability_extension":
            payload["tool_choice"] = {
                "type": "function",
                "function": {"name": "apply_capability_extension"},
            }
        elif requested_tool:
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
                with urllib.request.urlopen(request, timeout=180) as response:
                    result = json.loads(response.read().decode())
            except urllib.error.HTTPError as exc:
                details = exc.read().decode(errors="replace")
                raise RuntimeError(
                    f"Cloudflare API error ({exc.code}): {details}"
                ) from exc
            except TimeoutError as exc:
                raise RuntimeError(
                    "Cloudflare request timed out while waiting for the model response."
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

            if requested_tool == "get_system_boot_time" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-system-boot-time",
                    "type": "function",
                    "function": {
                        "name": "get_system_boot_time",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "get_system_memory_usage" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-system-memory-usage",
                    "type": "function",
                    "function": {
                        "name": "get_system_memory_usage",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "get_system_cpu_usage" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-system-cpu-usage",
                    "type": "function",
                    "function": {
                        "name": "get_system_cpu_usage",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "get_screen_state" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-screen-state",
                    "type": "function",
                    "function": {
                        "name": "get_screen_state",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "get_screen_brightness" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-screen-brightness",
                    "type": "function",
                    "function": {
                        "name": "get_screen_brightness",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "get_screen_brightness_mode" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-screen-brightness-mode",
                    "type": "function",
                    "function": {
                        "name": "get_screen_brightness_mode",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "get_screen_orientation" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-screen-orientation",
                    "type": "function",
                    "function": {
                        "name": "get_screen_orientation",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "get_media_volume" and loop_index == 0:
                tool_calls = [{"id": "requested-media-volume", "type": "function", "function": {"name": "get_media_volume", "arguments": "{}"}}]
                native_tool_calls = False

            if requested_tool == "get_screen_density" and loop_index == 0:
                tool_calls = [{"id": "requested-screen-density", "type": "function", "function": {"name": "get_screen_density", "arguments": "{}"}}]
                native_tool_calls = False

            if requested_tool == "get_screen_refresh_rate" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-screen-refresh-rate",
                    "type": "function",
                    "function": {
                        "name": "get_screen_refresh_rate",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "get_screen_resolution" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-screen-resolution",
                    "type": "function",
                    "function": {
                        "name": "get_screen_resolution",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "get_screen_timeout" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-screen-timeout",
                    "type": "function",
                    "function": {
                        "name": "get_screen_timeout",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "get_system_battery_status" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-system-battery-status",
                    "type": "function",
                    "function": {
                        "name": "get_system_battery_status",
                        "arguments": "{}",
                    },
                }]
                native_tool_calls = False

            if requested_tool == "get_system_swap_usage" and loop_index == 0:
                tool_calls = [{
                    "id": "requested-system-swap-usage",
                    "type": "function",
                    "function": {
                        "name": "get_system_swap_usage",
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