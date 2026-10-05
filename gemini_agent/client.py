"""Cloudflare Workers AI client for the minimal Nova agent."""

import json
import re
import os
from pathlib import Path
import urllib.error
import urllib.request
from collections.abc import Callable

from gemini_agent.tools import plan_capability_extension, send_android_keyevent, send_android_intent, resolve_android_intent, discover_android_ui_actions, validate_android_mechanism, execute_validated_android_mechanism, FIND_EXECUTABLE_DECLARATION, DIAGNOSE_COMMAND_FAILURE_DECLARATION, VERIFY_COMMAND_RESULT_DECLARATION, RETRY_COMMAND_DECLARATION, RECOVER_COMMAND_DECLARATION, RUN_ROOT_COMMAND_DECLARATION, GET_NETWORK_ADDRESSES_DECLARATION, GET_PROCESS_COMMAND_LINE_DECLARATION, GET_PROCESS_CPU_TIME_DECLARATION, GET_PROCESS_MEMORY_USAGE_DECLARATION, GET_PROCESS_NICE_DECLARATION, GET_PROCESS_EXECUTABLE_DECLARATION, GET_PROCESS_PARENT_NAME_DECLARATION, GET_PROCESS_START_TIME_DECLARATION, GET_PROCESS_STATUS_DECLARATION, GET_PROCESS_WORKING_DIRECTORY_DECLARATION, GET_SYSTEM_BATTERY_STATUS_DECLARATION, GET_WIFI_STATUS_DECLARATION, GET_BLUETOOTH_STATUS_DECLARATION, GET_AIRPLANE_MODE_DECLARATION, GET_SYSTEM_MEMORY_USAGE_DECLARATION, GET_SYSTEM_SCREEN_STATE_DECLARATION, GET_SYSTEM_SCREEN_BRIGHTNESS_DECLARATION, GET_SYSTEM_SCREEN_ORIENTATION_DECLARATION, GET_SYSTEM_SCREEN_RESOLUTION_DECLARATION, GET_SYSTEM_SCREEN_DENSITY_DECLARATION, GET_MEDIA_VOLUME_DECLARATION, GET_SYSTEM_SCREEN_REFRESH_RATE_DECLARATION, GET_SYSTEM_SCREEN_TIMEOUT_DECLARATION, GET_SYSTEM_BOOT_TIME_DECLARATION, GET_SYSTEM_CPU_USAGE_DECLARATION, GET_SYSTEM_MEMORY_USAGE_DECLARATION, GET_SYSTEM_SWAP_USAGE_DECLARATION, LIST_PROCESSES_DECLARATION, RUN_COMMAND_DECLARATION, TOOL_DECLARATIONS, TOOL_HANDLERS


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
        match = re.search(r"(?:mechanism|candidate)\s*[:=]\s*([^\n]+)", request_text, re.IGNORECASE)
        if match:
            return match.group(1).strip().strip("`")
        match = re.search(r"\b(intent|executable|service|ui):[^\s,]+", request_text, re.IGNORECASE)
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
        if any(phrase in user_text for phrase in ("execute validated android mechanism", "execute the validated android mechanism", "run the validated android mechanism")):
            return "execute_validated_android_mechanism"
        if ("validate" in user_text and "android mechanism" in user_text) or "check android mechanism" in user_text:
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