"""Cloudflare Workers AI client for the minimal Nova agent."""

import json
import re
import os
from pathlib import Path
import urllib.error
import urllib.request
from collections.abc import Callable

from gemini_agent.tools import plan_capability_extension, send_android_keyevent, send_android_intent, resolve_android_intent, discover_android_ui_actions, validate_android_mechanism, FIND_EXECUTABLE_DECLARATION, DIAGNOSE_COMMAND_FAILURE_DECLARATION, VERIFY_COMMAND_RESULT_DECLARATION, RETRY_COMMAND_DECLARATION, RECOVER_COMMAND_DECLARATION, RUN_ROOT_COMMAND_DECLARATION, GET_NETWORK_ADDRESSES_DECLARATION, GET_PROCESS_COMMAND_LINE_DECLARATION, GET_PROCESS_CPU_TIME_DECLARATION, GET_PROCESS_MEMORY_USAGE_DECLARATION, GET_PROCESS_NICE_DECLARATION, GET_PROCESS_EXECUTABLE_DECLARATION, GET_PROCESS_PARENT_NAME_DECLARATION, GET_PROCESS_START_TIME_DECLARATION, GET_PROCESS_STATUS_DECLARATION, GET_PROCESS_WORKING_DIRECTORY_DECLARATION, GET_SYSTEM_BATTERY_STATUS_DECLARATION, GET_WIFI_STATUS_DECLARATION, GET_BLUETOOTH_STATUS_DECLARATION, GET_AIRPLANE_MODE_DECLARATION, GET_SYSTEM_MEMORY_USAGE_DECLARATION, GET_SYSTEM_SCREEN_STATE_DECLARATION, GET_SYSTEM_SCREEN_BRIGHTNESS_DECLARATION, GET_SYSTEM_SCREEN_ORIENTATION_DECLARATION, GET_SYSTEM_SCREEN_RESOLUTION_DECLARATION, GET_SYSTEM_SCREEN_DENSITY_DECLARATION, GET_MEDIA_VOLUME_DECLARATION, GET_SYSTEM_SCREEN_REFRESH_RATE_DECLARATION, GET_SYSTEM_SCREEN_TIMEOUT_DECLARATION, GET_SYSTEM_BOOT_TIME_DECLARATION, GET_SYSTEM_CPU_USAGE_DECLARATION, GET_SYSTEM_MEMORY_USAGE_DECLARATION, GET_SYSTEM_SWAP_USAGE_DECLARATION, LIST_PROCESSES_DECLARATION, RUN_COMMAND_DECLARATION, TOOL_DECLARATIONS, TOOL_HANDLERS


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

    @staticmethod
    def _fill_extension_request(args: dict, request_text: str) -> dict:
        filled = dict(args)
        if not str(filled.get("request", "")).strip():
            filled["request"] = request_text
        return filled

    @staticmethod
    def _extract_mechanism(request_text: str) -> str:
        match = re.search(r"(?:mechanism|candidate)\\s*[:=]\\s*([^\\n]+)", request_text, re.IGNORECASE)
        if match:
            return match.group(1).strip().strip("`")
        match = re.search(r"\\b(intent|executable|service|ui):[^\\s,]+", request_text, re.IGNORECASE)
        if match:
            return match.group(0)
        return ""

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
        if any(phrase in user_text for phrase in ("discover android mechanisms", "discover android mechanism", "find android mechanisms")):
            return "discover_android_mechanisms"
        if any(phrase in user_text for phrase in ("validate android mechanism", "validate an android mechanism", "check android mechanism")):
            return "validate_android_mechanism"
        if any(phrase in user_text for phrase in ("resolve android intent", "resolve an android intent", "check android intent handler", "inspect android intent handler")):
            return "resolve_android_intent"
        if any(phrase in user_text for phrase in ("inspect android ui", "inspect the android ui", "inspect the current android ui", "inspect foreground ui", "inspect the current ui", "dump the android ui hierarchy")):
            return "inspect_android_ui"
        if any(phrase in user_text for phrase in ("inspect android ui", "inspect the android ui", "inspect foreground ui", "inspect the current ui", "dump the android ui hierarchy")):
            return "inspect_android_ui"
        if any(phrase in user_text for phrase in ("inspect foreground android component", "inspect foreground android app", "current foreground android component", "current foreground activity")):
            return "get_foreground_android_component"
        if any(phrase in user_text for phrase in ("discover android ui actions", "discover clickable android controls", "discover clickable android ui controls", "clickable android ui controls", "find clickable ui controls", "inspect clickable ui controls")):
            return "discover_android_ui_actions"
        if any(phrase in user_text for phrase in ("discover camera control", "camera control environment", "camera shutter mechanism")):
            return "discover_camera_control"
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
        if "send_android_intent" in user_text or "android intent" in user_text or "image capture intent" in user_text:
            return "send_android_intent"
        if "send_android_keyevent" in user_text or "android key event" in user_text or "camera key event" in user_text:
            return "send_android_keyevent"
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
                        excerpt = "\n".join(
                            f"{number + 1}: {lines[number]}"
                            for number in range(start, end)
                        )
                        if excerpt not in excerpts:
                            excerpts.append(excerpt)
                        break
            if excerpts:
                context.append("Relevant gemini_agent/tools.py excerpts:")
                context.extend(excerpts)

            # Give the model exact, copyable integration anchors. The model must
            # not have to reconstruct whitespace or guess where a declaration or
            # handler belongs.
            anchor_patterns = (
                "TOOL_DECLARATIONS = [",
                "TOOL_HANDLERS: dict[str, Callable[..., str]] = {",
            )
            for pattern in anchor_patterns:
                index = source.find(pattern)
                if index >= 0:
                    lines = source.splitlines()
                    line_index = source[:index].count("\n")
                    start = max(0, line_index)
                    end = min(len(lines), start + 18)
                    context.append(
                        f"Exact integration anchor: {pattern}"
                    )
                    context.append(
                        "\n".join(
                            f"{number + 1}: {lines[number]}"
                            for number in range(start, end)
                        )
                    )

        plan = plan_capability_extension(request)
        proposed_name = ""
        if "Proposed tool: " in plan:
            proposed_name = plan.split("Proposed tool: ", 1)[1].splitlines()[0].strip()
            if proposed_name.startswith("extend_"):
                proposed_name = proposed_name[len("extend_"):]
        handler_names = []
        try:
            namespace = {}
            exec(compile(source_path.read_text(encoding="utf-8"), str(source_path), "exec"), namespace)
            handlers = namespace.get("TOOL_HANDLERS", {})
            if isinstance(handlers, dict):
                handler_names = sorted(str(name) for name in handlers)
        except Exception:
            handler_names = []
        if handler_names:
            context.append("Exact existing TOOL_HANDLERS names:")
            context.append(", ".join(handler_names))
            context.append(
                "Implementation targets must be action-capable primitives. "
                "Do not select inspection, planning, orchestration, inventory, "
                "self-test, or diagnostic tools as implementation_target. "
                "The local transaction rejects those categories automatically."
            )

        context.append(
            "Use apply_capability_extension as a structured existing-tool composition transaction. "
            "Provide path gemini_agent/tools.py, implementation_kind='existing_tool', an exact existing "
            "implementation_target from the exact TOOL_HANDLERS list above, JSON object text in "
            "implementation_args, and a concise declaration_description. Do not provide function_source, "
            "old_text, or new_text. "
            f"HARD CONSTRAINT: the proposed capability name is exactly '{proposed_name}'. "
            "The implementation_target must match an existing TOOL_HANDLERS key character-for-character. "
            "Do not invent Android APIs, permissions, executables, services, or device behavior. "
            "The local transaction generates the new Python wrapper itself. If no existing local primitive "
            "can safely implement the capability, do not fabricate one."
        )
        return "\n".join(context)

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
        request_text = next(
            (
                item.get("content", "")
                for item in reversed(messages)
                if item.get("role") == "user"
            ),
            "",
        )
        if requested_tool == "inspect_android_ui":
            return str(self.tool_handlers["inspect_android_ui"]())
        if requested_tool == "get_foreground_android_component":
            return str(self.tool_handlers["get_foreground_android_component"]())
        if requested_tool == "discover_android_ui_actions":
            return str(self.tool_handlers["discover_android_ui_actions"]())
        if requested_tool == "validate_android_mechanism":
            return str(self.tool_handlers["validate_android_mechanism"](request=request_text, mechanism=self._extract_mechanism(request_text)))
        if requested_tool == "resolve_android_intent":
            normalized = request_text.upper()
            action = "STILL_IMAGE_CAMERA" if "STILL_IMAGE_CAMERA" in normalized else "IMAGE_CAPTURE"
            return str(self.tool_handlers["resolve_android_intent"](action=action))

        if requested_tool == "apply_capability_extension":
            inspection = self._extension_inspection_context(request_text)
            messages = [
                {"role": "system", "content": (
                    inspection
                    + "\nCall apply_capability_extension directly with the four structured arguments. "
                    + "Use function_source for the complete function body, not an old_text/new_text patch. "
                    + "Do not emit prose or XML."
                )},
                {"role": "user", "content": request_text},
            ]

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

            # Explicit self-extension requests are transactional. If the model
            # produces no proposal at all, stop here rather than burning tool rounds.
            if requested_tool == "apply_capability_extension" and not tool_calls and not content:
                return (
                    "Extension not applied: Cloudflare did not return a valid "
                    "capability-extension proposal. No code or device state was modified."
                )

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

            if requested_tool == "resolve_android_intent" and loop_index == 0:
                user_text = ""
                for item in reversed(payload["messages"]):
                    if item.get("role") == "user":
                        user_text = item.get("content", "")
                        break
                normalized = str(user_text).upper()
                action = "STILL_IMAGE_CAMERA" if "STILL_IMAGE_CAMERA" in normalized else "IMAGE_CAPTURE"
                tool_calls = [{
                    "id": "requested-resolve-android-intent",
                    "type": "function",
                    "function": {
                        "name": "resolve_android_intent",
                        "arguments": json.dumps({"action": action}),
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

            if requested_tool == "get_process_parent_name" and loop_index == 0:
                user_text = ""
                for item in reversed(payload["messages"]):
                    if item.get("role") == "user":
                        user_text = item.get("content", "")
                        break
                match = re.search(r"(?:pid|for\\s+pid|for|of)\\s+(\\d+)", str(user_text).strip(), re.IGNORECASE)
                if match:
                    tool_calls = [{
                        "id": "requested-process-parent-name",
                        "type": "function",
                        "function": {
                            "name": "get_process_parent_name",
                            "arguments": json.dumps({"pid": match.group(1)}),
                        },
                    }]
                    native_tool_calls = False

            if requested_tool == "get_process_working_directory" and loop_index == 0:
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
                        "id": "requested-process-working-directory",
                        "type": "function",
                        "function": {
                            "name": "get_process_working_directory",
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
                match = re.search(
                    r"run_command.*?run\s+[`\"]([^`\"]+)[`\"]",
                    str(user_text).strip(),
                    re.IGNORECASE,
                )
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

            if requested_tool == "diagnose_command_failure" and loop_index == 0:
                user_text = ""
                for item in reversed(payload["messages"]):
                    if item.get("role") == "user":
                        user_text = item.get("content", "")
                        break
                match = re.search(
                    r"diagnose_command_failure.*?command\\s+[\\\"']?(.+?)[\\\"']?\\s+with\\s+error\\s+[\\\"']?(.+?)[\\\"']?\\.?$",
                    str(user_text).strip(),
                    re.IGNORECASE,
                )
                if match:
                    tool_calls = [{
                        "id": "requested-diagnose-command-failure",
                        "type": "function",
                        "function": {
                            "name": "diagnose_command_failure",
                            "arguments": json.dumps({"command": match.group(1).strip(), "error": match.group(2).strip()}),
                        },
                    }]
                    native_tool_calls = False

            if requested_tool == "retry_command" and loop_index == 0:
                user_text = ""
                for item in reversed(payload["messages"]):
                    if item.get("role") == "user":
                        user_text = item.get("content", "")
                        break
                match = re.search(
                    r"retry_command.*?run\s+[`\"]([^`\"]+)[`\"]",
                    str(user_text).strip(),
                    re.IGNORECASE,
                )
                if match:
                    tool_calls = [{
                        "id": "requested-retry-command",
                        "type": "function",
                        "function": {
                            "name": "retry_command",
                            "arguments": json.dumps({"command": match.group(1).strip()}),
                        },
                    }]
                    native_tool_calls = False

            if requested_tool == "recover_command" and loop_index == 0:
                user_text = ""
                for item in reversed(payload["messages"]):
                    if item.get("role") == "user":
                        user_text = item.get("content", "")
                        break
                match = re.search(
                    r"recover_command.*?run\s+[`\"]([^`\"]+)[`\"]",
                    str(user_text).strip(),
                    re.IGNORECASE,
                )
                if match:
                    tool_calls = [{
                        "id": "requested-recover-command",
                        "type": "function",
                        "function": {
                            "name": "recover_command",
                            "arguments": json.dumps({"command": match.group(1).strip()}),
                        },
                    }]
                    native_tool_calls = False

            if requested_tool == "verify_command_result" and loop_index == 0:
                user_text = ""
                for item in reversed(payload["messages"]):
                    if item.get("role") == "user":
                        user_text = item.get("content", "")
                        break
                match = re.search(
                    r'verify_command_result.*?result\s+"([^"]+)"\s+with\s+expected\s+"([^"]+)"\.?$',
                    str(user_text).strip(),
                    re.IGNORECASE,
                )
                if match:
                    tool_calls = [{
                        "id": "requested-verify-command-result",
                        "type": "function",
                        "function": {
                            "name": "verify_command_result",
                            "arguments": json.dumps({"result": match.group(1), "expected": match.group(2)}),
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
                # Cloudflare's OpenAI-compatible endpoint requires function
                # arguments to be a JSON string. Normalize every tool-call
                # source, including XML/content-emitted calls, before sending
                # the conversation back for another tool round.
                normalized_tool_calls = []
                for tool_call in tool_calls:
                    normalized_tool_call = dict(tool_call)
                    function = dict(normalized_tool_call.get("function") or {})
                    arguments = function.get("arguments", "{}")
                    if isinstance(arguments, dict):
                        function["arguments"] = json.dumps(arguments)
                    elif arguments is None:
                        function["arguments"] = "{}"
                    elif not isinstance(arguments, str):
                        function["arguments"] = json.dumps(arguments)
                    normalized_tool_call["type"] = "function"
                    normalized_tool_call["function"] = function
                    normalized_tool_calls.append(normalized_tool_call)

                if native_tool_calls:
                    normalized_message = dict(message)
                    normalized_message["tool_calls"] = normalized_tool_calls
                    payload["messages"].append(normalized_message)
                else:
                    payload["messages"].append({
                        "role": "assistant",
                        "tool_calls": normalized_tool_calls,
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
                        if local_name == "apply_capability_extension":
                            args = self._fill_extension_request(args, request_text)
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

                    # Self-extension is transactional and must not enter an
                    # unbounded repair conversation with the model. One model
                    # proposal, one local transaction, then return the result.
                    if requested_tool == "apply_capability_extension":
                        return str(tool_result)

                    if requested_tool == "apply_capability_extension" and not str(tool_result).startswith("Extension status: source edit applied and transaction committed."):
                        payload["messages"].append({
                            "role": "user",
                            "content": (
                                "Previous extension attempt failed: "
                                + str(tool_result)
                                + ". Inspect the supplied repository context and call "
                                "apply_capability_extension again with a corrected existing "
                                "path and exact old_text."
                            ),
                        })

                # Deterministic explicit filesystem requests do not need a second
                # Cloudflare round-trip. Return the local tool result directly.
                if requested_tool in {"capability_inventory", "assess_capability_gap", "plan_capability_extension", "self_test", "discover_camera_control", "resolve_android_intent", "send_android_keyevent", "send_android_intent", "list_processes", "run_root_command", "run_command", "find_executable", "diagnose_command_failure", "verify_command_result", "retry_command", "recover_command", "path_exists", "get_file_access_time", "get_file_modified_time", "get_file_extension", "get_file_name", "get_file_stem", "get_file_permissions", "get_directory_entry_count", "get_directory_size", "count_file_lines", "get_disk_usage", "get_hostname", "get_system_info", "get_cpu_count", "get_process_id", "get_current_working_directory", "get_python_executable", "get_memory_usage", "get_temp_directory", "get_home_directory", "get_process_uptime", "get_process_thread_count", "get_parent_process_id", "get_process_group_id", "get_session_id", "get_user_id", "get_umask", "get_process_status", "get_process_command_line", "get_process_executable", "get_process_working_directory", "get_process_parent_name", "get_process_memory_usage", "get_system_uptime", "get_system_swap_usage", "get_system_boot_time", "get_system_cpu_usage", "get_system_memory_usage", "get_system_battery_status", "get_wifi_status", "get_bluetooth_status", "get_airplane_mode", "get_screen_state", "get_screen_brightness", "get_screen_brightness_mode", "get_screen_resolution", "get_screen_density", "get_media_volume", "get_screen_refresh_rate", "get_screen_timeout"} and loop_index == 0:
                    return str(tool_result)

                # Tool execution is Nova's responsibility. For an explicit
                # single-tool request, synthesize locally after one execution.
                # For a normal task, retain the tool set so Cloudflare can compose
                # bounded multi-step work from the observed result. The outer loop
                # caps the number of tool rounds and therefore bounds execution.
                if requested_tool == "apply_capability_extension":
                    if "Extension status: source edit applied and transaction committed." in str(tool_result):
                        return str(tool_result)
                    payload["tool_choice"] = {
                        "type": "function",
                        "function": {"name": "apply_capability_extension"},
                    }
                elif requested_tool:
                    payload.pop("tools", None)
                    payload.pop("tool_choice", None)
                else:
                    payload["tool_choice"] = "auto"
                continue

            elif not content:
                if requested_tool == "apply_capability_extension":
                    return (
                        "Extension not applied: Cloudflare did not return a valid "
                        "capability-extension proposal. No code or device state was modified."
                    )
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
        requested_tool = self._requested_local_tool(contents)
        normalized_prompt = str(prompt).upper()
        if (
            requested_tool == "resolve_android_intent"
            or "RESOLVE THE ANDROID IMAGE_CAPTURE INTENT" in normalized_prompt
            or "RESOLVE ANDROID INTENT" in normalized_prompt
        ):
            action = "STILL_IMAGE_CAMERA" if "STILL_IMAGE_CAMERA" in normalized_prompt else "IMAGE_CAPTURE"
            return str(self.tool_handlers["resolve_android_intent"](action=action))
        if requested_tool == "discover_android_ui_actions":
            return str(self.tool_handlers["discover_android_ui_actions"]())
        return self._generate_cloudflare(contents, system_instruction)