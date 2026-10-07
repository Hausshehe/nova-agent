"""Cloudflare Workers AI client for the minimal Nova agent."""

import json
import re
import os
from pathlib import Path
import urllib.error
import urllib.request
from collections.abc import Callable

from gemini_agent.android_ui import execute_validated_android_ui_mechanism
from gemini_agent.goal_state import GoalState, start_goal_state
from gemini_agent.goal_progress import observe_goal_progress
from gemini_agent.goal_completion import verify_goal_completion
from gemini_agent.tools import analyze_capability_history, autonomously_repair_capability, plan_capability_extension, send_android_keyevent, send_android_intent, resolve_android_intent, discover_android_ui_actions, rank_android_mechanism_candidates, validate_android_mechanism, select_capability_repair_candidate, apply_capability_repair, execute_validated_android_mechanism, execute_android_mechanism, recover_android_mechanism, FIND_EXECUTABLE_DECLARATION, DIAGNOSE_COMMAND_FAILURE_DECLARATION, VERIFY_COMMAND_RESULT_DECLARATION, RETRY_COMMAND_DECLARATION, RECOVER_COMMAND_DECLARATION, RUN_ROOT_COMMAND_DECLARATION, GET_NETWORK_ADDRESSES_DECLARATION, GET_PROCESS_COMMAND_LINE_DECLARATION, GET_PROCESS_CPU_TIME_DECLARATION, GET_PROCESS_MEMORY_USAGE_DECLARATION, GET_PROCESS_NICE_DECLARATION, GET_PROCESS_EXECUTABLE_DECLARATION, GET_PROCESS_PARENT_NAME_DECLARATION, GET_PROCESS_START_TIME_DECLARATION, GET_PROCESS_STATUS_DECLARATION, GET_PROCESS_WORKING_DIRECTORY_DECLARATION, GET_SYSTEM_BATTERY_STATUS_DECLARATION, GET_WIFI_STATUS_DECLARATION, GET_BLUETOOTH_STATUS_DECLARATION, GET_AIRPLANE_MODE_DECLARATION, GET_SYSTEM_MEMORY_USAGE_DECLARATION, GET_SYSTEM_SCREEN_STATE_DECLARATION, GET_SYSTEM_SCREEN_BRIGHTNESS_DECLARATION, GET_SYSTEM_SCREEN_ORIENTATION_DECLARATION, GET_SYSTEM_SCREEN_RESOLUTION_DECLARATION, GET_SYSTEM_SCREEN_DENSITY_DECLARATION, GET_MEDIA_VOLUME_DECLARATION, GET_SYSTEM_SCREEN_REFRESH_RATE_DECLARATION, GET_SYSTEM_SCREEN_TIMEOUT_DECLARATION, GET_SYSTEM_BOOT_TIME_DECLARATION, GET_SYSTEM_CPU_USAGE_DECLARATION, GET_SYSTEM_MEMORY_USAGE_DECLARATION, GET_SYSTEM_SWAP_USAGE_DECLARATION, LIST_PROCESSES_DECLARATION, RUN_COMMAND_DECLARATION, TOOL_DECLARATIONS, TOOL_HANDLERS


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
        self.goal_state: GoalState | None = None

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
    def _parse_android_mechanism_candidates(discovery: str) -> list[str]:
        """Parse bounded mechanism lines without assuming values contain no spaces."""
        candidates = []
        allowed = {"intent", "ui-text", "ui", "executable", "service"}
        for line in str(discovery).splitlines():
            stripped = line.strip().strip(chr(96)).strip()
            if ":" not in stripped:
                continue
            kind, value = stripped.split(":", 1)
            kind = kind.strip().lower()
            value = value.strip().strip(chr(96)).strip()
            if kind in allowed and value:
                candidates.append(f"{kind}:{value}")
        return candidates

    @staticmethod
    def _rank_android_mechanism_candidates(
        request: str, candidates: list[str]
    ) -> list[str]:
        """Compatibility wrapper around Nova's shared Android mechanism ranking."""
        return rank_android_mechanism_candidates(request, candidates)

    @staticmethod
    def _parse_tool_arguments(arguments) -> dict:
        if arguments is None:
            return {}
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str) and not arguments.strip():
            return {}
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
        match = re.search(r"\b(intent|executable|service|ui-text|ui):[^\s,]+", request_text, re.IGNORECASE)
        if match:
            return match.group(0).rstrip(".,;:!?")
        match = re.search(r"(?:mechanism|candidate)\s*[:=]\s*([^\n]+)", request_text, re.IGNORECASE)
        if match:
            return match.group(1).strip().strip("`")
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
        # A request referring to the newly generated capability without naming it
        # must resolve to the actual generated wrapper, not an adjacent primitive.
        if re.search(r"\bnewly\s+generated\b", user_text, re.IGNORECASE) and re.search(
            r"\bcapabilit(?:y|ies)\b", user_text, re.IGNORECASE
        ):
            generated_names = []
            for name, handler in TOOL_HANDLERS.items():
                if getattr(handler, "__nova_generated_capability__", False):
                    generated_names.append(name)
                    continue
                code = getattr(handler, "__code__", None)
                if code is not None and "_run_android_mechanism_extension" in code.co_names:
                    generated_names.append(name)
                elif code is not None and "_run_extension_primitive" in code.co_names:
                    generated_names.append(name)
            if generated_names:
                declaration_by_name = {
                    declaration["name"]: declaration
                    for declaration in TOOL_DECLARATIONS
                    if isinstance(declaration, dict) and isinstance(declaration.get("name"), str)
                }
                stop_words = {
                    "the", "newly", "generated", "capability", "to", "use", "device",
                    "and", "then", "open", "report", "exactly", "what", "happened",
                }
                request_terms = {
                    token for token in re.findall(r"[a-z0-9_]+", user_text)
                    if token not in stop_words
                }
                scored = []
                for index, name in enumerate(generated_names):
                    declaration = declaration_by_name.get(name, {})
                    metadata = " ".join(
                        str(value)
                        for value in (
                            name,
                            declaration.get("description", ""),
                        )
                    ).lower()
                    candidate_terms = set(re.findall(r"[a-z0-9_]+", metadata))
                    score = len(request_terms & candidate_terms)
                    scored.append((score, index, name))
                return max(scored)[2]

        if any(phrase in user_text for phrase in (
            "select the goal next step",
            "select a goal next step",
            "choose the next step for the goal",
            "choose a goal-directed next step",
        )):
            return "select_goal_next_step"
        if any(phrase in user_text for phrase in (
            "establish a goal contract",
            "establish goal contract",
            "set the goal contract",
            "set goal contract",
        )):
            return "establish_goal_contract"
        if any(phrase in user_text for phrase in (
            "learn from verified android experience",
            "record verified android experience",
            "persist verified android experience",
        )):
            return "record_verified_android_experience"
        if any(phrase in user_text for phrase in (
            "rank android mechanisms",
            "rank the android mechanisms",
            "rank discovered android mechanisms",
        )):
            return "rank_android_mechanism_candidates"
        if any(phrase in user_text for phrase in (
            "record verified experience",
            "record a verified experience",
            "persist verified experience",
            "persist a verified experience",
            "learn from verified experience",
        )):
            # Compound requests must stay in the normal decision loop so that
            # the record step can be followed by selection, execution, and
            # automatic outcome learning rather than terminating early.
            if not re.search(r"then\s+use\s+(?:the\s+)?normal\s+decision\s+process", user_text):
                return "record_verified_experience_tool"
        if any(phrase in user_text for phrase in (
            "select verified strategy",
            "choose strategy using verified experience",
            "choose a strategy using verified experience",
        )):
            return "select_verified_strategy_tool"
        if any(phrase in user_text for phrase in (
            "rank verified experience",
            "rank verified experiences",
            "rank candidates using verified experience",
        )):
            return "rank_verified_experience_candidates"
        if any(phrase in user_text for phrase in (
            "autonomously repair",
            "autonomous self-repair",
            "run the self-repair workflow",
            "run autonomous self-repair",
            "repair this capability automatically",
        )):
            return "autonomously_repair_capability"
        if any(phrase in user_text for phrase in (
            "diagnose a capability failure",
            "diagnose a failure of",
            "diagnose capability failure",
            "capability failure diagnosis",
        )):
            return "diagnose_capability_failure"
        if (
            "select a repair candidate" in user_text
            or "select repair candidate" in user_text
            or "repair-candidate selection" in user_text
            or "repair candidate selection" in user_text
        ):
            return "select_capability_repair_candidate"
        if (
            "apply the capability repair" in user_text
            or "apply capability repair" in user_text
            or "execute the bounded repair transaction" in user_text
            or "bounded repair transaction" in user_text
        ):
            return "apply_capability_repair"

        # Explicitly named generated capabilities are local actions. Resolve them
        # before Cloudflare so provider-side argument generation cannot reinterpret
        # the request or execute an adjacent primitive.
        action_request = bool(
            re.search(r"\b(?:execute|run|use|verify|test)\b", user_text, re.IGNORECASE)
            and re.search(r"\bcapabilit(?:y|ies)\b", user_text, re.IGNORECASE)
        )
        if action_request:
            generated_names = []
            for name, handler in TOOL_HANDLERS.items():
                if getattr(handler, "__nova_generated_capability__", False):
                    generated_names.append(name)
                    continue
                code = getattr(handler, "__code__", None)
                if code is not None and any(
                    marker in code.co_names
                    for marker in ("_run_android_mechanism_extension", "_run_extension_primitive")
                ):
                    generated_names.append(name)
            for name in sorted(generated_names, key=len, reverse=True):
                if re.search(rf"\b{re.escape(name.lower())}\b", user_text, re.IGNORECASE):
                    return name

        if "self-test" in user_text or "self test" in user_text:
            return "self_test"
        if any(phrase in user_text for phrase in ("discover android mechanisms", "discover android mechanism", "find android mechanisms")):
            return "discover_android_mechanisms"
        if any(phrase in user_text for phrase in (
            "recover_android_mechanism",
            "use recover_android_mechanism",
            "use the generic android recovery capability",
            "generic android recovery capability",
        )):
            return "recover_android_mechanism"
        if any(phrase in user_text for phrase in (
            "execute validated android mechanism",
            "execute the validated android mechanism",
            "run the validated android mechanism",
            "android mechanism execution capability",
            "android mechanism execution tool",
            "use the android mechanism execution capability",
        )):
            return "execute_validated_android_mechanism"
        if any(phrase in user_text for phrase in ("execute validated android ui mechanism", "execute the validated android ui mechanism", "run the validated android ui mechanism")):
            return "execute_validated_android_ui_mechanism"
        if (
            "plan a capability extension" in user_text
            or "plan an extension" in user_text
            or "how would you add this capability" in user_text
        ):
            return "plan_capability_extension"
        if any(phrase in user_text for phrase in (
            "apply capability extension",
            "apply the capability extension",
            "apply the extension",
        )):
            return "apply_capability_extension"
        if (
            ("extend yourself" in user_text or "self-extend" in user_text or "self extension" in user_text)
            and any(phrase in user_text for phrase in ("add a capability", "add this capability", "new capability", "missing capability", "capability"))
        ):
            return "apply_capability_extension"
        if ("validate" in user_text and "android mechanism" in user_text) or "check android mechanism" in user_text:
            return "validate_android_mechanism"
        if any(phrase in user_text for phrase in ("resolve android intent", "resolve an android intent", "check android intent handler", "inspect android intent handler")):
            return "resolve_android_intent"
        if any(phrase in user_text for phrase in ("inspect android ui", "inspect the android ui", "inspect the current android ui", "inspect foreground ui", "inspect the current ui", "dump the android ui hierarchy", "android ui inspection")):
            return "inspect_android_ui"
        if any(phrase in user_text for phrase in ("inspect android ui", "inspect the android ui", "inspect foreground ui", "inspect the current ui", "dump the android ui hierarchy")):
            return "inspect_android_ui"
        if any(phrase in user_text for phrase in ("inspect foreground android component", "inspect foreground android app", "current foreground android component", "current foreground activity")):
            return "get_foreground_android_component"
        if any(phrase in user_text for phrase in ("discover android ui actions", "discover clickable android controls", "discover clickable android ui controls", "clickable android ui controls", "find clickable ui controls", "inspect clickable ui controls")):
            return "discover_android_ui_actions"
        if any(phrase in user_text for phrase in ("discover camera control", "camera control environment", "camera shutter mechanism")):
            return "discover_camera_control"
        if any(phrase in user_text for phrase in (
            "apply capability extension",
            "apply the capability extension",
            "apply the extension",
        )):
            return "apply_capability_extension"
        if (
            ("extend yourself" in user_text or "self-extend" in user_text or "self extension" in user_text)
            and any(phrase in user_text for phrase in ("add a capability", "add this capability", "new capability", "missing capability", "capability"))
        ):
            return "apply_capability_extension"
        if any(phrase in user_text for phrase in ("plan a capability extension", "plan an extension", "extend yourself", "add this capability", "how would you add this capability")):
            return "plan_capability_extension"
        if any(phrase in user_text for phrase in ("do i have a capability", "do you have a capability", "is there a tool", "can you do this", "can you do that", "do you support this")):
            return "assess_capability_gap"
        if any(phrase in user_text for phrase in (
            "analyze capability history",
            "analyze the capability history",
            "analyze persisted capability history",
            "repair verification decision",
            "analyze repair verification",
        )):
            return "analyze_capability_history"
        if (
            ("record a" in user_text or "record an" in user_text or "record the" in user_text)
            and "outcome" in user_text
            and "ledger" in user_text
        ):
            return "record_capability_outcome"
        if ("outcome history" in user_text or "capability history" in user_text) and (
            "read" in user_text or "retrieve" in user_text or "show" in user_text
        ):
            return "get_capability_outcome_history"
        if "capability inventory" in user_text or "capabilities" in user_text or "what tools" in user_text:
            return "capability_inventory"
        if "assess_capability_gap" in user_text:
            return "assess_capability_gap"
        if "find_executable" in user_text:
            return "find_executable"
        # When a compound request explicitly says to execute run_command, that
        # execution is the initial action. Later mentions of diagnosis/recovery are
        # downstream handling instructions and must not hijack the initial route.
        if "run_command" in user_text and re.search(
            r"\b(?:use|execute|run)\s+run_command\b.*\b(?:execute|run)\b",
            user_text,
            re.IGNORECASE,
        ):
            return "run_command"
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

        discovery = ""
        try:
            discovery = str(self.tool_handlers["discover_android_mechanisms"](request=request))
        except Exception as exc:
            discovery = f"Android mechanism discovery failed: {exc}"
        context.append("Fresh Android mechanism discovery for this request:")
        context.append(discovery)
        context.append(
            "Use apply_capability_extension as a bounded self-extension transaction. "
            "For an existing local primitive, use implementation_kind='existing_tool' and an exact "
            "TOOL_HANDLERS target. For a discovered Android mechanism, use implementation_kind="
            "'android_mechanism', implementation_target equal to the exact validated mechanism string "
            "from the discovery results, and implementation_args='{}'. Prefer a discovered mechanism "
            "over inventing an API, permission, executable, service, or device behavior. The transaction "
            "validates the Android mechanism again before writing code and runs the deterministic test suite "
            "before committing. Do not provide function_source, old_text, or new_text. "
            f"HARD CONSTRAINT: the proposed capability name is exactly '{proposed_name}'. "
            "If no viable mechanism or existing primitive can safely implement the capability, do not "
            "fabricate one and do not modify the repository."
        )
        return "\n".join(context)

    def _strategy_execution_name(self, strategy: str) -> str:
        """Return the registered executable tool for a strategy, or an empty string."""
        candidate = self._CLOUD_TOOL_NAMES.get(str(strategy).strip(), str(strategy).strip())
        if not candidate or candidate not in self.tool_handlers:
            return ""
        if not any(
            isinstance(declaration, dict) and declaration.get("name") == candidate
            for declaration in self.tool_declarations
        ):
            return ""
        return candidate


    def _coordinate_tool_failure(
        self,
        local_name: str,
        args: dict,
        tool_result: str,
        request_text: str,
        learning_request: str = "",
    ) -> str:
        """Classify one failed tool outcome and hand it to an existing bounded recovery path."""

        result = str(tool_result)
        failed = bool(
            re.search(r"\bExit code:\s*[1-9]\d*\b", result)
            or re.search(r"\bTool error\s*:", result, re.IGNORECASE)
            or re.search(r"\bOutcome:\s*(?:FAILED|failure)\b", result, re.IGNORECASE)
        )
        if not failed:
            return result
        if local_name == "run_command":
            command = str(args.get("command", "")).strip()
            diagnosis = self.tool_handlers["diagnose_command_failure"](command=command, error=result)
            expected = ""
            expected_match = re.search(
                r"expected(?:\s+text|\s+postcondition)?(?:\s+is|\s*[:=])?\s*['\"]([^'\"]+)['\"]",
                request_text,
                re.IGNORECASE,
            )
            if expected_match:
                expected = expected_match.group(1).strip()
            recovery = str(self.tool_handlers["recover_command"](command=command, expected=expected))
            failure_learning = ""
            if re.search(r"\b(?:Exit code:\s*[1-9]\d*|Tool error\s*:|Outcome\s*:\s*FAILED)", result, re.IGNORECASE):
                from gemini_agent.learning import record_verified_failure
                failure_learning = record_verified_failure(
                    learning_request or request_text,
                    local_name,
                    result,
                    domain="general",
                )
            learning_result = ""
            if re.search(r"(?:Post-action verification|Verification|Postcondition)\s*:\s*VERIFIED\b|\bOutcome:\s*VERIFIED\b", recovery, re.IGNORECASE):
                from gemini_agent.learning import record_verified_experience, record_verified_failure
                learning_result = record_verified_experience(
                    learning_request or request_text,
                    "recover_command",
                    recovery,
                    domain="general",
                )
            diagnostic_report = recovery if diagnosis in recovery else f"{diagnosis}\\n{recovery}"
            if failure_learning:
                diagnostic_report = f"{diagnostic_report}\\nFailure learning:\\n{failure_learning}"
            if learning_result:
                diagnostic_report = f"{diagnostic_report}\\nRecovery learning:\\n{learning_result}"
            return (
                "Automatic tool recovery:\\n"
                f"Failed tool: {local_name}\\n"
                f"Original tool result:\\n{result}\\n"
                f"{diagnostic_report}"
            )
        if local_name in {"execute_android_mechanism", "execute_validated_android_mechanism"}:
            mechanism = str(args.get("mechanism", "")).strip()
            if mechanism:
                recovery = str(self.tool_handlers["recover_android_mechanism"](
                    request=request_text, mechanism=mechanism, verification=result
                ))
                failure_learning = ""
                if re.search(r"\b(?:Exit code:\s*[1-9]\d*|Tool error\s*:|Outcome\s*:\s*FAILED)\b", result, re.IGNORECASE):
                    from gemini_agent.learning import record_verified_failure
                    failure_learning = record_verified_failure(
                        learning_request or request_text,
                        local_name,
                        result,
                        domain="general",
                    )
                learning_result = ""
                if re.search(r"(?:Post-action verification|Verification|Postcondition)\s*:\s*VERIFIED\b|\bOutcome:\s*VERIFIED\b", recovery, re.IGNORECASE):
                    from gemini_agent.learning import record_verified_experience, record_verified_failure
                    learning_result = record_verified_experience(
                        learning_request or request_text,
                        "recover_android_mechanism",
                        recovery,
                        domain="general",
                    )
                recovery_report = recovery
                if learning_result:
                    recovery_report = f"{recovery_report}\\nRecovery learning:\\n{learning_result}"
                return (
                    "Automatic tool recovery:\\n"
                    f"Failed tool: {local_name}\n"
                    f"Original tool result:\\n{result}\n"
                    f"{recovery_report}"
                )
        return (
            "Automatic tool recovery:\n"
            f"Failed tool: {local_name}\n"
            f"Original tool result:\n{result}\n"
            "Recovery: no bounded recovery path is registered for this tool.\n"
            "Outcome: FAILED\n"
            "Action: stop safely."
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

        request_text = ""
        for item in reversed(contents):
            if item.get("role") == "user":
                request_text = " ".join(
                    part.get("text", "")
                    for part in item.get("parts", [])
                    if isinstance(part, dict) and isinstance(part.get("text"), str)
                )
                break
        prompt = request_text
        prompt_text = request_text

        # Verified experience is part of Nova's normal decision loop. When a task
        # presents multiple candidate strategies, deterministically apply the existing
        # generic selector before the provider reasons about execution. Learned experience
        # is preference only: it never substitutes for validation, execution, or
        # postcondition verification.
        decision_policy = (
            "Nova decision policy: when multiple candidate strategies are explicitly "
            "available for the same goal, use the verified-experience preference supplied "
            "by Nova before deciding what to execute. Treat learned experience only as a "
            "preference from sufficiently similar VERIFIED experience. Never treat learned "
            "experience as proof of current viability or success; validate the selected "
            "mechanism/capability and independently verify execution."
        )
        if system_instruction:
            messages[0]["content"] = str(messages[0]["content"]) + "\n\n" + decision_policy
        else:
            messages.insert(0, {"role": "system", "content": decision_policy})

        # Deterministic normal-loop bridge. This is deliberately generic: it only handles
        # explicit candidate-strategy lists, applies the existing selector, and feeds its
        # result back as preference context. It does not execute a strategy or treat the
        # learned result as proof of viability.
        strategy_candidates = []
        strategy_goal = ""
        selected_strategy = ""
        strategy_seed_tool = ""
        candidate_patterns = (
            r'candidate strategies?\s*[:=]?\s*["\']([^"\']+)["\']\s*(?:,|and)\s*["\']([^"\']+)["\']',
            r'between\s+strategy\s+["\']([^"\']+)["\']\s+and\s+strategy\s+["\']([^"\']+)["\']',
        )
        for pattern in candidate_patterns:
            candidate_match = re.search(pattern, request_text, re.IGNORECASE)
            if candidate_match:
                strategy_candidates = [candidate_match.group(1).strip(), candidate_match.group(2).strip()]
                break
        if strategy_candidates:
            goal_match = re.search(
                r'((?:recover|solve|handle|complete|perform)\s+(?:a|an|the)?\s*.+?)(?=\.\s*(?:I have|You have|There are)|$)',
                request_text,
                re.IGNORECASE,
            )
            normal_request_match = re.search(
                r'\bthen\s+use\s+(?:the\s+)?normal\s+decision\s+process\s+for\s+request\s+["\']([^"\']+)["\']',
                request_text,
                re.IGNORECASE,
            )
            if normal_request_match:
                goal = normal_request_match.group(1).strip()
            else:
                goal = goal_match.group(1).strip() if goal_match else request_text.strip()
            strategy_goal = goal
            from gemini_agent.learning import select_verified_strategy
            selection = select_verified_strategy(goal, strategy_candidates)
            selected_match = re.search(
                r"(?m)^Verified strategy selection:\s*(.+)$",
                selection,
            )
            selected_strategy = selected_match.group(1).strip() if selected_match else ""
            selected_execution_name = self._strategy_execution_name(selected_strategy)
            if not selected_execution_name:
                executable_candidates = [
                    candidate
                    for candidate in strategy_candidates
                    if self._strategy_execution_name(candidate)
                ]
                if executable_candidates:
                    strategy_candidates = executable_candidates
                    selection = select_verified_strategy(goal, strategy_candidates)
                    selected_match = re.search(
                        r"(?m)^Verified strategy selection:\s*(.+)$",
                        selection,
                    )
                    selected_strategy = selected_match.group(1).strip() if selected_match else ""
                    selected_execution_name = self._strategy_execution_name(selected_strategy)
                if not selected_execution_name:
                    self.last_tool_calls.append({
                        "name": "select_verified_strategy_tool",
                        "args": {"request": goal, "candidates": strategy_candidates, "domain": "general"},
                        "result": selection,
                    })
                    return (
                        "Verified strategy selection blocked before execution.\n"
                        f"Selected strategy: {selected_strategy or 'NONE'}\n"
                        "Reason: the selected strategy has no registered executable tool.\n"
                        "Safety boundary: verified experience is preference only; Nova will not "
                        "send an unregistered strategy to the provider or invent an execution mechanism.\n"
                        "Outcome: STOPPED SAFELY"
                    )
            messages[0]["content"] = str(messages[0]["content"]) + (
                "\n\nVerified strategy preference from Nova:\n" + selection +
                "\nThis is preference only. Independently validate and verify any execution."
            )
            self.last_tool_calls.append({
                "name": "select_verified_strategy_tool",
                "args": {"request": goal, "candidates": strategy_candidates, "domain": "general"},
                "result": selection,
            })

        unnamed_generated_capability_request = bool(
            re.search(r"\\b(?:use|execute|run|verify|test)\\b", request_text, re.IGNORECASE)
            and re.search(r"\\bcapabilit(?:y|ies)\\b", request_text, re.IGNORECASE)
            and not any(
                getattr(handler, "__nova_generated_capability__", False)
                and re.search(rf"\\b{re.escape(name)}\\b", request_text, re.IGNORECASE)
                for name, handler in self.tool_handlers.items()
            )
        )

        requested_tool = self._requested_local_tool(contents)
        # A compound strategy-selection workflow must stay in the normal decision
        # loop. Do not let a nested strategy name such as verify_command_result
        # hijack the whole request into a single local verifier call.
        if strategy_candidates:
            requested_tool = None
        # Resolve explicitly named generated capabilities from the live client
        # registry before any provider round-trip. This keeps execution local and
        # prevents provider-side argument generation from reinterpreting a repair
        # verification request.
        lower_prompt = prompt_text.lower()
        # Compound autonomous workflows own the whole request. Do not let a
        # nested instruction such as "execute the repaired capability" hijack
        # routing to the generated capability itself.
        if (
            requested_tool != "autonomously_repair_capability"
            and re.search(r"\b(?:execute|run|use|verify|test)\b", lower_prompt)
            and re.search(r"\bcapabilit(?:y|ies)\b", lower_prompt)
        ):
            generated_names = []
            for name, handler in self.tool_handlers.items():
                if getattr(handler, "__nova_generated_capability__", False):
                    generated_names.append(name)
                    continue
                code = getattr(handler, "__code__", None)
                if code is not None and any(marker in code.co_names for marker in ("_run_android_mechanism_extension", "_run_extension_primitive")):
                    generated_names.append(name)
            for name in sorted(generated_names, key=len, reverse=True):
                if re.search(rf"\b{re.escape(name)}\b", lower_prompt):
                    requested_tool = name
                    break
        if requested_tool == "select_goal_next_step":
            goal_match = re.search(r"\bgoal\s+[\"']([^\"']+)[\"']", request_text, re.IGNORECASE)
            success_match = re.search(r"\bsuccess\s+condition\s+[\"']([^\"']+)[\"']", request_text, re.IGNORECASE)
            status_match = re.search(r"\bgoal\s+status\s*[:=]\s*(ACTIVE|VERIFIED|FAILED)", request_text, re.IGNORECASE)
            progress_match = re.search(r"\bprogress\s+status\s*[:=]\s*(PROGRESS|BLOCKED|INCONCLUSIVE)", request_text, re.IGNORECASE)
            reason_match = re.search(r"\bprogress\s+reason\s+[\"']([^\"']+)[\"']", request_text, re.IGNORECASE)
            candidates_match = re.search(r"\bcandidates?\s*[:=]\s*(.+?)(?=\s+Report|\s*$)", request_text, re.IGNORECASE | re.DOTALL)
            if not all((goal_match, success_match, status_match, progress_match, reason_match, candidates_match)):
                return "Selecting a goal next step requires a goal, success condition, goal status, progress status, progress reason, and candidates."
            candidates = [item.strip().strip("\"'") for item in candidates_match.group(1).split(",") if item.strip()]
            result = str(self.tool_handlers[requested_tool](
                goal=goal_match.group(1).strip(), success_condition=success_match.group(1).strip(),
                goal_status=status_match.group(1).upper(), progress_status=progress_match.group(1).upper(),
                progress_reason=reason_match.group(1).strip(), candidates=candidates,
            ))
            self.last_tool_calls.append({"name": requested_tool, "args": {"goal": goal_match.group(1).strip(), "success_condition": success_match.group(1).strip(), "goal_status": status_match.group(1).upper(), "progress_status": progress_match.group(1).upper(), "progress_reason": reason_match.group(1).strip(), "candidates": candidates}, "result": result})
            return result

        if requested_tool == "establish_goal_contract":
            goal_match = re.search(r"\bfor\s+[\"']([^\"']+)[\"']", request_text, re.IGNORECASE)
            success_match = re.search(
                r"\bsuccess\s+condition\s+[\"']([^\"']+)[\"']",
                request_text,
                re.IGNORECASE,
            )
            if not goal_match or not success_match:
                return "Establishing a goal contract requires a quoted goal and quoted success condition."
            goal = goal_match.group(1).strip()
            success_condition = success_match.group(1).strip()
            result = str(
                self.tool_handlers["establish_goal_contract"](
                    goal=goal,
                    success_condition=success_condition,
                )
            )
            self.goal_state = start_goal_state(goal, success_condition)
            result += (
                "\nRuntime goal state: ACTIVE\n"
                "Runtime evidence: 0 entries\n"
                "Runtime state changed: Yes\n"
                "Action executed: No"
            )
            self.last_tool_calls.append({
                "name": requested_tool,
                "args": {"goal": goal, "success_condition": success_condition},
                "result": result,
            })
            continuation = re.search(r"\b(?:then|after that|next)\b", request_text, re.IGNORECASE)
            if not continuation:
                return result
            continuation_text = request_text[continuation.end():].strip()
            continuation_contents = [{"role": "user", "parts": [{"text": continuation_text}]}]
            next_tool = self._requested_local_tool(continuation_contents)
            if not next_tool:
                # The goal contract is established, but no explicit next tool was
                # requested. Leave routing open so the goal-directed execution bridge
                # can select the next bounded capability.
                requested_tool = None
            else:
                requested_tool = next_tool
            continuation_handler = self.tool_handlers.get(requested_tool)
            if continuation_handler is not None:
                import inspect
                parameters = inspect.signature(continuation_handler).parameters
                required = [
                    parameter for parameter in parameters.values()
                    if parameter.default is inspect.Parameter.empty
                    and parameter.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
                ]
                if not required:
                    continuation_result = str(continuation_handler())
                    self.goal_state.add_evidence(continuation_result)
                    observation = observe_goal_progress(goal, success_condition, continuation_result)
                    self.goal_state.progress_status = observation.status
                    self.goal_state.progress_reason = observation.reason
                    completion = verify_goal_completion(
                        goal, success_condition, continuation_result
                    )
                    if completion.status == "VERIFIED":
                        self.goal_state.status = "VERIFIED"
                    elif completion.status == "FAILED":
                        self.goal_state.status = "FAILED"
                    return (
                        result
                        + "\nGoal progress observation: " + observation.status
                        + "\nGoal progress reason: " + observation.reason
                        + "\nGoal completion verification: " + completion.status
                        + "\nGoal completion reason: " + completion.reason
                        + "\nRuntime goal status: " + self.goal_state.status
                        + "\nObserved tool: " + requested_tool
                        + "\nObserved result: " + continuation_result
                    )
            messages.append({
                "role": "system",
                "content": (
                    "Runtime goal contract established for this turn.\\n"
                    f"Goal: {goal}\\n"
                    f"Success condition: {success_condition}\\n"
                    "The runtime state is ACTIVE. Any tool outcome must be observed as goal evidence; "
                    "do not claim final completion unless a later bounded completion verifier explicitly proves it."
                ),
            })

        # Goal-directed execution bridge: use the existing bounded next-step selector
        # to choose one relevant registered capability when a runtime goal is active.
        goal_selected_action = ""
        if self.goal_state is not None and not requested_tool and not strategy_candidates:
            goal_declarations = self._relevant_tool_declarations(contents)
            goal_candidates = [
                str(declaration.get("name", "")).strip()
                for declaration in goal_declarations
                if isinstance(declaration, dict)
                and str(declaration.get("name", "")).strip()
                not in {
                    "establish_goal_contract", "select_goal_next_step",
                    "self_test", "capability_inventory", "assess_capability_gap",
                }
            ]
            if goal_candidates:
                from gemini_agent.goal_next_step import select_goal_next_step
                goal_selection = select_goal_next_step(
                    self.goal_state.goal,
                    self.goal_state.success_condition,
                    self.goal_state.status,
                    self.goal_state.progress_status,
                    self.goal_state.progress_reason,
                    goal_candidates,
                )
                if goal_selection.action == "STOP":
                    return (
                        "Goal-directed next step: STOP\\n"
                        f"Reason: {goal_selection.reason}\\n"
                        "No goal-directed action was executed."
                    )
                if goal_selection.action in self.tool_handlers:
                    goal_selected_action = goal_selection.action
                    self.last_tool_calls.append({
                        "name": "select_goal_next_step",
                        "args": {
                            "goal": self.goal_state.goal,
                            "success_condition": self.goal_state.success_condition,
                            "goal_status": self.goal_state.status,
                            "progress_status": self.goal_state.progress_status,
                            "progress_reason": self.goal_state.progress_reason,
                            "candidates": goal_candidates,
                        },
                        "result": (
                            f"Next step: {goal_selection.action}\\n"
                            f"Reason: {goal_selection.reason}"
                        ),
                    })
                    messages[0]["content"] = str(messages[0]["content"]) + (
                        "\\n\\nGoal-directed next-step selection:\\n"
                        f"Selected action: {goal_selected_action}\\n"
                        f"Reason: {goal_selection.reason}\\n"
                        "Execute this selected action once, observe its result, and do not claim "
                        "goal completion unless the bounded completion verifier establishes it."
                    )

        if requested_tool == "select_verified_strategy_tool":
            request_match = re.search(r'(?:for|request)\s+(?:strategy\s+)?["\']([^"\']+)["\']', request_text, re.IGNORECASE)
            candidates_match = re.search(r'candidates?\s*(?::|=)?\s*(.+?)(?=\s+Do not|\s+Report|$)', request_text, re.IGNORECASE | re.DOTALL)
            if not request_match or not candidates_match:
                return "Selecting a verified strategy requires a request and strategy candidates."
            candidates = [c.strip().rstrip(".").strip().strip('"').strip("'").strip() for c in candidates_match.group(1).split(",") if c.strip()]
            domain_match = re.search(r'\bdomain\s*[:=]\s*([A-Za-z0-9_-]+)', request_text, re.IGNORECASE)
            args = {"request": request_match.group(1).strip(), "candidates": candidates, "domain": domain_match.group(1).strip() if domain_match else "general"}
            result = str(self.tool_handlers[requested_tool](**args))
            self.last_tool_calls.append({"name": requested_tool, "args": args, "result": result})
            return result

        if requested_tool == "record_verified_experience_tool":
            request_match = re.search(
                r'(?:for|request)\s+(?:experience\s+)?["\']([^"\']+)["\']\s+(?:using|with)\s+(?:strategy\s+)?',
                request_text, re.IGNORECASE,
            )
            strategy_match = re.search(
                r'(?:strategy|candidate)\s*(?::|=|\s)\s*([^\s,;]+)',
                request_text, re.IGNORECASE,
            )
            verification_match = re.search(
                r"(?:verification|evidence)\s*(?::|=)?\s*(?:\"([^\"]+)\"|'([^']+)'|(.+?))(?=\s+Then\s+rank|\s+Do not|\s+Report|$)",
                request_text, re.IGNORECASE | re.DOTALL,
            )
            domain_match = re.search(r'\bdomain\s*[:=]\s*([A-Za-z0-9_-]+)', request_text, re.IGNORECASE)
            if not request_match or not strategy_match or not verification_match:
                return "Recording a verified experience requires request, strategy, and verification evidence."
            args = {
                "request": request_match.group(1).strip(),
                "strategy": strategy_match.group(1).strip().rstrip("."),
                "verification": next(group.strip() for group in verification_match.groups() if group),
                "domain": domain_match.group(1).strip() if domain_match else "general",
            }
            result = str(self.tool_handlers["record_verified_experience_tool"](**args))
            self.last_tool_calls.append({"name": "record_verified_experience_tool", "args": args, "result": result})
            rank_match = re.search(
                r'rank\s+verified\s+experiences?\s+for\s+request\s+["\']([^"\']+)["\']',
                request_text, re.IGNORECASE,
            )
            candidates = []
            if rank_match:
                candidate_text = request_text[rank_match.end():]
                candidate_match = re.search(r'candidates?(?:\s*[:=]|\s+)\s*(.+?)(?=\s+Do not|\s+Report|$)', candidate_text, re.IGNORECASE | re.DOTALL)
                if candidate_match:
                    candidates = [c.strip().strip('"').strip("'").rstrip(".").strip().strip('"').strip("'") for c in candidate_match.group(1).split(",") if c.strip()]
                    candidates = list(dict.fromkeys(candidates))
            if rank_match and candidates:
                ranked = self.tool_handlers["rank_verified_experience_candidates"](
                    request=rank_match.group(1).strip(),
                    candidates=candidates,
                    domain=args["domain"],
                )
                self.last_tool_calls.append({"name": "rank_verified_experience_candidates", "args": {"request": rank_match.group(1).strip(), "candidates": candidates, "domain": args["domain"]}, "result": ranked})
                return result + "\n" + str(ranked)
            return result
        if requested_tool == "record_verified_android_experience":
            request_match = re.search(
                r'(?:for|request)\s+(?:capability\s+)?["\']([^"\']+)["\']\s+(?:using|with)',
                request_text,
                re.IGNORECASE,
            )
            if not request_match:
                request_match = re.search(
                    r'(?:for|request)\s+(?:capability\s+)?(.+?)\s+(?:using|with)\s+(?:mechanism\s+)?(?:intent|ui-text|ui):',
                    request_text,
                    re.IGNORECASE,
                )
            mechanism_match = re.search(
                r"((?:intent|ui-text|ui):[^\s,]+)",
                request_text,
                re.IGNORECASE,
            )
            verification_match = re.search(
                r"(?:verification|evidence)\s*[:=]\s*(.+?)(?=\s+Then\s+rank|\s+Do not|\s+Report|$)",
                request_text,
                re.IGNORECASE | re.DOTALL,
            )
            if not request_match or not mechanism_match or not verification_match:
                return "Recording a verified Android experience requires request, mechanism, and verification evidence."
            record_request = request_match.group(1).strip()
            record_mechanism = mechanism_match.group(1).strip()
            record_verification = verification_match.group(1).strip()
            result = str(self.tool_handlers["record_verified_android_experience"](
                request=record_request,
                mechanism=record_mechanism,
                verification=record_verification,
            ))
            self.last_tool_calls.append({
                "name": "record_verified_android_experience",
                "args": {
                    "request": record_request,
                    "mechanism": record_mechanism,
                    "verification": record_verification,
                },
                "result": result,
            })
            rank_request_match = re.search(
                r'rank\s+Android\s+mechanisms\s+for\s+request\s+["\']([^"\']+)["\']',
                request_text,
                re.IGNORECASE,
            )
            rank_candidates = []
            for candidate in re.findall(
                r"(?:intent|ui-text|ui):[^\s,;]+",
                request_text,
                re.IGNORECASE,
            ):
                normalized = candidate.rstrip(".")
                if normalized not in rank_candidates:
                    rank_candidates.append(normalized)
            if rank_request_match and rank_candidates:
                ranked = self.tool_handlers["rank_android_mechanism_candidates"](
                    request=rank_request_match.group(1).strip(),
                    candidates=rank_candidates,
                )
                self.last_tool_calls.append({
                    "name": "rank_android_mechanism_candidates",
                    "args": {
                        "request": rank_request_match.group(1).strip(),
                        "candidates": rank_candidates,
                    },
                    "result": ranked,
                })
                return result + "\n" + str(ranked)
            return result
        if requested_tool == "rank_android_mechanism_candidates":
            request_match = re.search(
                r"(?:for|request)\s+(.+?)\s+(?:candidates?|mechanisms?)\s*[:=]",
                request_text,
                re.IGNORECASE,
            )
            candidates = re.findall(
                r"(?:intent|ui-text|ui):[^\s,;]+",
                request_text,
                re.IGNORECASE,
            )
            if not request_match or not candidates:
                return "Android mechanism ranking requires a request and at least one bounded mechanism candidate."
            result = str(self.tool_handlers["rank_android_mechanism_candidates"](
                request=request_match.group(1).strip(),
                candidates=candidates,
            ))
            self.last_tool_calls.append({
                "name": "rank_android_mechanism_candidates",
                "args": {"request": request_match.group(1).strip(), "candidates": candidates},
                "result": result,
            })
            return result
        if requested_tool == "autonomously_repair_capability":
            match = re.search(
                r"(?:for|of)\s+capability\s+[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?",
                request_text,
                re.IGNORECASE,
            )
            if not match:
                match = re.search(
                    r"(?:the\s+)?([A-Za-z_][A-Za-z0-9_]*)\s+capability\b",
                    request_text,
                    re.IGNORECASE,
                )
            capability = match.group(1) if match else ""
            evidence_match = re.search(
                r"(?:failure evidence|supplied failure evidence|evidence)\s*[:=]\s*(.+?)(?=\s+Do not|\s+Report|$)",
                request_text,
                re.IGNORECASE | re.DOTALL,
            )
            evidence = evidence_match.group(1).strip() if evidence_match else ""
            if not capability or not evidence:
                return "Autonomous self-repair requires an explicit capability name and supplied failure evidence."
            result = str(autonomously_repair_capability(capability=capability, failure_evidence=evidence))
            self.last_tool_calls.append({
                "name": "autonomously_repair_capability",
                "args": {"capability": capability, "failure_evidence": evidence},
                "result": result,
            })
            return result
        if (
            requested_tool != "accept_verified_capability_repair"
            and re.search(r"\baccept\b", lower_prompt, re.IGNORECASE)
            and re.search(r"\brepair(?:ed)?\b", lower_prompt, re.IGNORECASE)
            and re.search(r"\bcapabilit(?:y|ies)\b", lower_prompt, re.IGNORECASE)
        ):
            generated_names = [
                name for name, handler in self.tool_handlers.items()
                if getattr(handler, "__nova_generated_capability__", False)
            ]
            for name in sorted(generated_names, key=len, reverse=True):
                if re.search(rf"\b{re.escape(name)}\b", lower_prompt, re.IGNORECASE):
                    acceptance = str(
                        self.tool_handlers["accept_verified_capability_repair"](capability=name)
                    )
                    self.last_tool_calls.append({
                        "name": "accept_verified_capability_repair",
                        "args": {"capability": name},
                        "result": acceptance,
                    })
                    return acceptance
        if requested_tool in self.tool_handlers and getattr(self.tool_handlers[requested_tool], "__nova_generated_capability__", False):
            tool_result = self.tool_handlers[requested_tool]()
            self.last_tool_calls.append({"name": requested_tool, "args": {}, "result": tool_result})
            result_text = str(tool_result)
            recorder = self.tool_handlers.get("record_capability_repair_verification")
            if recorder is not None and (
                "Post-action verification:" in result_text
                or re.search(r"Verification\s*:", result_text, re.IGNORECASE)
            ):
                record_result = str(recorder(requested_tool, result_text))
                self.last_tool_calls.append({
                    "name": "record_capability_repair_verification",
                    "args": {"capability": requested_tool, "verification": result_text},
                    "result": record_result,
                })
                result_text += "\\n" + record_result
            return result_text
        if requested_tool == "analyze_capability_history":
            match = re.search(
                r"(?:for|of)\s+capability\s+[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?",
                prompt_text,
                re.IGNORECASE,
            )
            capability = match.group(1) if match else ""
            if not capability:
                match = re.search(
                    r"analy[sz]e(?:\s+the)?\s+capability\s+([A-Za-z_][A-Za-z0-9_]*)",
                    prompt_text,
                    re.IGNORECASE,
                )
                capability = match.group(1) if match else ""
            if not capability:
                return "Capability history analysis requires an explicit capability name."
            result = str(analyze_capability_history(capability))
            self.last_tool_calls.append({
                "name": "analyze_capability_history",
                "args": {"capability": capability},
                "result": result,
            })
            return result

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
        if requested_tool == "get_foreground_android_component":
            result = str(self.tool_handlers["get_foreground_android_component"]())
            self.last_tool_calls.append({"name": requested_tool, "args": {}, "result": result})
            return result
        if requested_tool == "inspect_android_ui":
            selector_match = re.search(r"\b(ui-text|ui):[^\s,]+", prompt, re.IGNORECASE)
            selector = selector_match.group(0).rstrip(".,;:!?") if selector_match else ""
            result = str(self.tool_handlers["inspect_android_ui"](selector=selector))
            self.last_tool_calls.append({"name": requested_tool, "args": {"selector": selector}, "result": result})
            return result
        if requested_tool == "validate_android_mechanism":
            mechanism = self._extract_mechanism(request_text)
            if not mechanism:
                return "Mechanism validation requires an explicit mechanism such as intent:IMAGE_CAPTURE."
            return str(self.tool_handlers["validate_android_mechanism"](request=request_text, mechanism=mechanism))
        if requested_tool == "execute_validated_android_ui_mechanism":
            mechanism = self._extract_mechanism(prompt)
            if not mechanism:
                return "UI mechanism execution requires an explicit mechanism such as ui:<resource-id>."
            return str(self.tool_handlers["execute_validated_android_ui_mechanism"](request=prompt, mechanism=mechanism))
        if requested_tool == "record_capability_outcome":
            capability_match = re.search(
                r"\bfor\s+capability\s+[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?",
                request_text,
                re.IGNORECASE,
            )
            stage_match = re.search(r"\bstage\s+[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?", request_text, re.IGNORECASE)
            status_match = re.search(r"\bstatus\s+[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?", request_text, re.IGNORECASE)
            evidence_match = re.search(
                r"evidence\s+[\"']([^\"']+)[\"']", request_text, re.IGNORECASE
            )
            capability = capability_match.group(1) if capability_match else ""
            stage = stage_match.group(1) if stage_match else ""
            status = status_match.group(1) if status_match else ""
            evidence = evidence_match.group(1).strip() if evidence_match else ""
            if not all((capability, stage, status, evidence)):
                return "Capability outcome recording requires explicit capability, stage, status, and quoted evidence."
            recorded = str(self.tool_handlers["record_capability_outcome"](
                capability=capability, stage=stage, status=status, evidence=evidence
            ))
            self.last_tool_calls.append({
                "name": "record_capability_outcome",
                "args": {"capability": capability, "stage": stage, "status": status, "evidence": evidence},
                "result": recorded,
            })
            if re.search(r"\bread back\b|\bretrieve\b|\bmost recent outcome history\b", request_text, re.IGNORECASE):
                history = str(self.tool_handlers["get_capability_outcome_history"](capability=capability))
                self.last_tool_calls.append({
                    "name": "get_capability_outcome_history",
                    "args": {"capability": capability},
                    "result": history,
                })
                return recorded + "\n" + history
            return recorded
        if requested_tool == "get_capability_outcome_history":
            match = re.search(
                r"(?:history|outcomes?)\s+(?:for|of)\s+[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?",
                request_text,
                re.IGNORECASE,
            )
            capability = match.group(1) if match else ""
            if not capability:
                return "Capability outcome history requires an explicit capability name."
            result = str(self.tool_handlers["get_capability_outcome_history"](capability=capability))
            self.last_tool_calls.append({
                "name": "get_capability_outcome_history",
                "args": {"capability": capability},
                "result": result,
            })
            return result

        if requested_tool == "autonomously_repair_capability":
            match = re.search(
                r"(?:for|of)\s+capability\s+[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?",
                request_text,
                re.IGNORECASE,
            )
            if not match:
                match = re.search(
                    r"(?:the\s+)?([A-Za-z_][A-Za-z0-9_]*)\s+capability\b",
                    request_text,
                    re.IGNORECASE,
                )
            capability = match.group(1) if match else ""
            evidence_match = re.search(
                r"(?:failure evidence|supplied failure evidence|evidence)\s*[:=]\s*(.+?)(?=\s+Do not|\s+Report|$)",
                request_text,
                re.IGNORECASE | re.DOTALL,
            )
            evidence = evidence_match.group(1).strip() if evidence_match else ""
            if not capability or not evidence:
                return "Autonomous self-repair requires an explicit capability name and supplied failure evidence."
            result = str(autonomously_repair_capability(capability=capability, failure_evidence=evidence))
            self.last_tool_calls.append({
                "name": "autonomously_repair_capability",
                "args": {"capability": capability, "failure_evidence": evidence},
                "result": result,
            })
            return result

        if requested_tool == "diagnose_capability_failure":
            match = re.search(
                r"\bof\s+(?:the\s+)?(?:existing\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s+capability\b",
                request_text,
                re.IGNORECASE,
            )
            if not match:
                match = re.search(
                    r"\b(?:capability|tool)\s+(?:named\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\b",
                    request_text,
                    re.IGNORECASE,
                )
            capability = match.group(1) if match else ""
            evidence_match = re.search(
                r"(?:evidence|supplied evidence)(?:\s+as\s+genuinely\s+\w+)?\s*[:=]\s*(.+?)(?=\s+(?:diagnose|determine|do not|report)\b|$)",
                request_text,
                re.IGNORECASE | re.DOTALL,
            )
            evidence = evidence_match.group(1).strip() if evidence_match else ""
            if not capability or not evidence:
                return "Capability failure diagnosis requires an explicit capability name and supplied failure evidence."
            result = self.tool_handlers["diagnose_capability_failure"](
                capability=capability,
                failure_evidence=evidence,
            )
            self.last_tool_calls.append({
                "name": "diagnose_capability_failure",
                "args": {"capability": capability, "failure_evidence": evidence},
                "result": result,
            })
            return str(result)

        if requested_tool == "select_capability_repair_candidate":
            match = re.search(
                r"\b(?:for|of|the)\s+(?:the\s+)?(?:existing\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s+capability\b",
                request_text,
                re.IGNORECASE,
            )
            if not match:
                match = re.search(
                    r"\b(?:capability|tool)\s+(?:named\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\b",
                    request_text,
                    re.IGNORECASE,
                )
            capability = match.group(1) if match else ""
            diagnosis_match = re.search(
                r"(?:after\s+this\s+read-only\s+diagnosis|diagnosis)\s*:\s*(.+?)(?=\s+Treat\s+the\s+supplied|\s+Use\s+read-only|\s+Do\s+not|\s+Determine\b|$)",
                request_text,
                re.IGNORECASE | re.DOTALL,
            )
            diagnosis = diagnosis_match.group(1).strip() if diagnosis_match else ""
            if not capability or not diagnosis:
                return "Capability repair-candidate selection requires an explicit capability name and read-only diagnosis."
            result = self.tool_handlers["select_capability_repair_candidate"](capability=capability, diagnosis=diagnosis)
            self.last_tool_calls.append({
                "name": "select_capability_repair_candidate",
                "args": {"capability": capability, "diagnosis": diagnosis},
                "result": result,
            })
            return str(result)

        if requested_tool == "apply_capability_repair":
            match = re.search(
                r"\b(?:for|of|the)\s+(?:the\s+)?(?:existing\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s+capability\b",
                request_text,
                re.IGNORECASE,
            )
            if not match:
                match = re.search(
                    r"\b(?:capability|tool)\s+(?:named\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\b",
                    request_text,
                    re.IGNORECASE,
                )
            capability = match.group(1) if match else ""
            candidate_match = re.search(
                r"\b(RESTORE_GENERATED_CAPABILITY)\b",
                request_text,
                re.IGNORECASE,
            )
            candidate = candidate_match.group(1) if candidate_match else ""
            if not capability or not candidate:
                return "Capability repair requires an explicit capability name and bounded repair candidate."
            result = self.tool_handlers["apply_capability_repair"](
                capability=capability,
                candidate=candidate,
            )
            self.last_tool_calls.append({
                "name": "apply_capability_repair",
                "args": {"capability": capability, "candidate": candidate},
                "result": result,
            })
            return str(result)

        if requested_tool == "recover_android_mechanism":
            mechanism = self._extract_mechanism(request_text)
            verification_match = re.search(
                r"(?:post-action\s+)?verification(?:\s+as\s+genuinely\s+\w+)?\s+for\s+this\s+test:\s*(.+?)(?=\s+(?:the\s+request\s+goal|request\s+goal|report)\s*:|$)",
                request_text,
                re.IGNORECASE | re.DOTALL,
            )
            if not verification_match:
                verification_match = re.search(
                    r"(?:verification|post-action verification)\s*[:=]\s*(.+?)(?=\s+(?:the\s+request\s+goal|request\s+goal|report)\s*:|$)",
                    request_text,
                    re.IGNORECASE | re.DOTALL,
                )
            verification = verification_match.group(1).strip() if verification_match else ""
            if not mechanism or not verification:
                return (
                    "Android mechanism recovery requires both an explicit mechanism "
                    "and supplied verification evidence."
                )
            result = self.tool_handlers["recover_android_mechanism"](
                request=request_text,
                mechanism=mechanism,
                verification=verification,
            )
            self.last_tool_calls.append({
                "name": "recover_android_mechanism",
                "args": {
                    "request": request_text,
                    "mechanism": mechanism,
                    "verification": verification,
                },
                "result": result,
            })
            return str(result)
        if requested_tool == "execute_validated_android_mechanism":
            mechanism = self._extract_mechanism(request_text)
            if not mechanism:
                try:
                    discovery = str(
                        self.tool_handlers["discover_android_mechanisms"](
                            request=request_text
                        )
                    )
                    candidates = self._parse_android_mechanism_candidates(discovery)
                    for candidate in candidates:
                        validation = str(
                            self.tool_handlers["validate_android_mechanism"](
                                request=request_text,
                                mechanism=candidate,
                            )
                        )
                        if "Status: VIABLE" in validation:
                            mechanism = candidate
                            break
                except (RuntimeError, ValueError, TypeError):
                    mechanism = ""
            if not mechanism:
                return (
                    "Mechanism execution could not select a viable discovered mechanism. "
                    "No Android mechanism was executed."
                )
            handler = self.tool_handlers.get("execute_android_mechanism")
            if handler is None:
                handler = self.tool_handlers["execute_validated_android_mechanism"]
            return str(handler(request=request_text, mechanism=mechanism))
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
        if strategy_candidates and selected_strategy:
            strategy_seed_tool = (
                "record_verified_experience_tool"
                if re.search(
                    r"\bfirst\s+record\s+(?:a\s+)?verified\s+experience\b",
                    request_text,
                    re.IGNORECASE,
                )
                else ""
            )
            if strategy_seed_tool:
                seed_request_match = re.search(
                    r'(?:for|request)\s+(?:experience\s+)?["\']([^"\']+)["\']\s+(?:using|with)\s+(?:strategy\s+)?',
                    request_text,
                    re.IGNORECASE,
                )
                seed_strategy_match = re.search(
                    r'(?:strategy|candidate)\s*(?::|=|\s)\s*([^\s,;]+)',
                    request_text,
                    re.IGNORECASE,
                )
                seed_verification_match = re.search(
                    r'(?:verification|evidence)\s*(?::|=)?\s*(?:"([^"]+)"|\'([^\']+)\'|(.+?))(?=\s+Then\s+|\s+Do not|\s+Report|$)',
                    request_text,
                    re.IGNORECASE | re.DOTALL,
                )
                if seed_request_match and seed_strategy_match and seed_verification_match:
                    seed_args = {
                        "request": seed_request_match.group(1).strip(),
                        "strategy": seed_strategy_match.group(1).strip().rstrip("."),
                        "verification": next(group.strip() for group in seed_verification_match.groups() if group),
                        "domain": "general",
                    }
                    seed_result = str(self.tool_handlers["record_verified_experience_tool"](**seed_args))
                    self.last_tool_calls.append({
                        "name": "record_verified_experience_tool",
                        "args": seed_args,
                        "result": seed_result,
                    })
            declarations = [
                d for d in self.tool_declarations
                if d["name"] == selected_strategy
            ]
        if goal_selected_action:
            declarations = [
                d for d in self.tool_declarations
                if d["name"] == goal_selected_action
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
        elif goal_selected_action:
            payload["tool_choice"] = {
                "type": "function",
                "function": {"name": self._CLOUD_TOOL_NAMES.get(goal_selected_action, goal_selected_action)},
            }
        elif strategy_candidates and selected_strategy:
            selected_cloud_name = self._CLOUD_TOOL_NAMES.get(selected_strategy, selected_strategy)
            payload["tool_choice"] = {
                "type": "function",
                "function": {"name": selected_cloud_name},
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
                    raw_response = response.read().decode()
                try:
                    result = json.loads(raw_response)
                except json.JSONDecodeError as exc:
                    if loop_index < 2:
                        continue
                    raise RuntimeError(
                        "Cloudflare returned an invalid JSON response after retries: "
                        f"{exc}"
                    ) from exc
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
                    r"(?:run_command.*?(?:execute|run)\s+(?:the\s+)?(?:safe\s+)?command\s+|(?:execute|run)\s+(?:the\s+)?(?:safe\s+)?command\s+)(?:\\)?[`\"](.+?)(?:\\)?[`\"](?:\.|$)",
                    str(user_text).strip(),
                    re.IGNORECASE,
                )
                if match:
                    tool_calls = [{
                        "id": "requested-run-command",
                        "type": "function",
                        "function": {
                            "name": "run_command",
                            "arguments": json.dumps({"command": match.group(1).strip().replace("\\\"", "\"")}),
                        },
                    }]
                    native_tool_calls = False

            if requested_tool == "diagnose_command_failure" and loop_index == 0:
                user_text = ""
                for item in reversed(payload["messages"]):
                    if item.get("role") == "user":
                        user_text = item.get("content", "")
                        break
                match = re.search(                    r"diagnose_command_failure.*?command\\s+[\\\"']?(.+?)[\\\"']?\\s+with\\s+error\\s+[\\\"']?(.+?)[\\\"']?\\.?$",
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
                        },                    }]
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

                    args = {}
                    try:
                        args = self._parse_tool_arguments(function.get("arguments", "{}"))
                        if local_name == "plan_capability_extension":
                            args["request"] = request_text
                            args["inspect_reality"] = True
                        if local_name == "apply_capability_extension":
                            args = self._fill_extension_request(args, request_text)
                            if str(args.get("implementation_kind", "")).strip().lower() == "android_mechanism":
                                target = str(args.get("implementation_target", "")).strip()
                                target = re.sub(r"^(intent|executable|service|ui-text|ui):\s+", r"\1:", target, flags=re.IGNORECASE)
                                extracted = self._extract_mechanism(target)
                                if extracted:
                                    args["implementation_target"] = extracted
                        if requested_tool == "recover_command" and "expected postcondition" in prompt.lower():
                            command_match = re.search(r"`([^`]+)`", prompt)
                            expected_match = re.search(
                                r"expected postcondition(?:\s+is|\s*[:=])?\s*`([^`]+)`",
                                prompt,
                                re.IGNORECASE,
                            )
                            if command_match and expected_match:
                                args = {
                                    "command": command_match.group(1).strip(),
                                    "expected": expected_match.group(1).strip(),
                                }
                        # Preserve explicit command arguments from the user's goal when
                        # the selected executable strategy is run_command. Provider-generated
                        # arguments are advisory here: they must not reinterpret a concrete
                        # command such as "dumpsys -l" as "run_command -l".
                        if selected_strategy and local_name == selected_strategy == "run_command":
                            command_match = re.search(
                                r'\b(?:using\s+)?command\s+["\\\']([^"\\\']+)["\\\']',
                                request_text,
                                re.IGNORECASE,
                            )
                            if command_match:
                                args = {"command": command_match.group(1).strip()}
                        # Satisfy required observation inputs for the selected strategy
                        # before invoking it. The rule is schema-driven: when the selected
                        # tool requires a "result" and the request supplies a bounded command,
                        # execute that prerequisite observation once and pass its result into
                        # the selected strategy. The selected strategy itself still executes once.
                        if selected_strategy and local_name == selected_strategy:
                            selected_declaration = next(
                                (
                                    declaration
                                    for declaration in self.tool_declarations
                                    if declaration.get("name") == local_name
                                ),
                                None,
                            )
                            required = set(
                                (selected_declaration or {})
                                .get("parameters", {})
                                .get("required", [])
                            )
                            current_result = str(args.get("result", "")).strip()
                            if "result" in required and (
                                not current_result or "Exit code:" not in current_result
                            ):
                                command_match = re.search(
                                    r'\busing\s+command\s+["\']([^"\']+)["\']',
                                    request_text,
                                    re.IGNORECASE,
                                )
                                if not command_match:
                                    command_match = re.search(
                                        r'\bcommand\s+["\']([^"\']+)["\']',
                                        request_text,
                                        re.IGNORECASE,
                                    )
                                if command_match:
                                    args["result"] = self.tool_handlers["run_command"](
                                        command=command_match.group(1).strip()
                                    )
                        tool_result = handler(**args)
                        tool_result = self._coordinate_tool_failure(
                            local_name=local_name,
                            args=args,
                            tool_result=str(tool_result),
                            request_text=request_text,
                            learning_request=strategy_goal,
                        )

                    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                        if local_name == "run_command":
                            recovery_args = dict(args)
                            if not str(recovery_args.get("command", "")).strip():
                                command_match = re.search(
                                    r'\b(?:using\s+)?command\s+["\']([^"\']+)["\']',
                                    request_text,
                                    re.IGNORECASE,
                                )
                                if command_match:
                                    recovery_args["command"] = command_match.group(1).strip()
                            if str(recovery_args.get("command", "")).strip():
                                args = recovery_args
                                tool_result = self._coordinate_tool_failure(
                                    local_name="run_command",
                                    args=recovery_args,
                                    tool_result=f"Tool error: {exc}",
                                    request_text=request_text,
                                    learning_request=strategy_goal,
                                )
                            else:
                                args = {}
                                tool_result = f"Tool error: {exc}"
                        else:
                            args = {}
                            tool_result = f"Tool error: {exc}"

                    if self.goal_state is not None:
                        self.goal_state.add_evidence(str(tool_result))
                        observation = observe_goal_progress(
                            self.goal_state.goal,
                            self.goal_state.success_condition,
                            str(tool_result),
                        )
                        self.goal_state.progress_status = observation.status
                        self.goal_state.progress_reason = observation.reason
                        completion = verify_goal_completion(
                            self.goal_state.goal,
                            self.goal_state.success_condition,
                            str(tool_result),
                        )
                        if completion.status == "VERIFIED":
                            self.goal_state.status = "VERIFIED"
                        elif completion.status == "FAILED":
                            self.goal_state.status = "FAILED"
                        tool_result = (
                            str(tool_result)
                            + "\\nGoal progress observation: "
                            + observation.status
                            + "\\nGoal progress reason: "
                            + observation.reason
                            + "\\nGoal completion verification: "
                            + completion.status
                            + "\\nGoal completion reason: "
                            + completion.reason
                            + "\\nRuntime goal status: "
                            + self.goal_state.status
                        )
                        if goal_selected_action and self.goal_state.status == "VERIFIED":
                            return str(tool_result)


                    trace = {"name": local_name, "args": args, "result": tool_result}
                    if (
                        selected_strategy
                        and strategy_goal
                        and local_name == selected_strategy
                        and re.search(
                            r"(?:Post-action verification|Verification)\s*:\s*VERIFIED\b",
                            str(tool_result),
                            re.IGNORECASE,
                        )
                    ):
                        from gemini_agent.learning import record_verified_experience, record_verified_failure
                        learning_result = record_verified_experience(
                            strategy_goal,
                            selected_strategy,
                            str(tool_result),
                            domain="general",
                        )
                        trace["verified_experience_learning"] = learning_result
                    if "expression" in args:
                        trace["expression"] = str(args["expression"])
                    self.last_tool_calls.append(trace)

                    payload["messages"].append({
                        "role": "tool",
                        "tool_call_id": tool_call.get("id", ""),
                        "content": str(tool_result),
                    })

                    # Once a requested seed experience is recorded, the selected
                    # strategy becomes the only executable tool in this workflow.
                    # This prevents the provider from substituting a prerequisite
                    # observation or another candidate for Nova's selected strategy.
                    if (
                        strategy_candidates
                        and selected_strategy
                        and strategy_seed_tool
                        and local_name == strategy_seed_tool
                    ):
                        selected_cloud_name = self._CLOUD_TOOL_NAMES.get(
                            selected_strategy, selected_strategy
                        )
                        payload["tools"] = [
                            tool
                            for tool in payload.get("tools", [])
                            if tool.get("function", {}).get("name") == selected_cloud_name
                        ]
                        payload["tool_choice"] = {
                            "type": "function",
                            "function": {"name": selected_cloud_name},
                        }

                    # The selected strategy has now executed. Its result is authoritative
                    # for this decision step. Do not offer the same strategy another turn,
                    # or the provider can repeat execution until the outer call budget dies.
                    if (
                        strategy_candidates
                        and selected_strategy
                        and local_name == selected_strategy
                    ):
                        payload.pop("tools", None)
                        payload.pop("tool_choice", None)

                    # Self-extension is transactional and must not enter an
                    # unbounded repair conversation with the model. One model
                    # proposal, one local transaction, then return the result.
                    if requested_tool == "apply_capability_extension":
                        return str(tool_result)

                    # An explicitly named capability request is a single local
                    # action. Execute it once and return its result instead of
                    # sending the same action back to Cloudflare for another round.
                    explicit_capability_use = bool(
                        re.search(r"\buse\s+(?:the\s+)?[\w.-]+\s+capability\b", request_text, re.IGNORECASE)
                        or (
                            local_name
                            and re.search(r"\buse\b", request_text, re.IGNORECASE)
                            and re.search(r"\bcapabilit(?:y|ies)\b", request_text, re.IGNORECASE)
                            and local_name.lower() in request_text.lower()
                        )
                    )
                    if (
                        explicit_capability_use
                        and requested_tool == local_name
                        and not strategy_candidates
                    ):
                        return str(tool_result)

                    # Dynamically added capabilities are local extensions, not
                    # ordinary Cloudflare planning tools. When the user explicitly
                    # asks to use one, execute it once and return its result.
                    builtin_names = {declaration["name"] for declaration in TOOL_DECLARATIONS}
                    dynamic_capability_use = bool(
                        local_name
                        and local_name not in builtin_names
                        and re.search(r"\bcapabilit(?:y|ies)\b", request_text, re.IGNORECASE)
                        and (
                            local_name.lower() in request_text.lower()
                            or re.search(r"\bnewly\s+generated\b", request_text, re.IGNORECASE)
                        )
                    )
                    if dynamic_capability_use or (
                        unnamed_generated_capability_request
                        and getattr(handler, "__nova_generated_capability__", False)
                    ):
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
                elif strategy_candidates and selected_strategy:
                    if local_name == selected_strategy:
                        # The selected strategy has already executed in this round.
                        # It is evidence now, not another executable option.
                        payload.pop("tools", None)
                        payload.pop("tool_choice", None)
                    else:
                        selected_cloud_name = self._CLOUD_TOOL_NAMES.get(
                            selected_strategy, selected_strategy
                        )
                        payload["tools"] = [
                            tool
                            for tool in payload.get("tools", [])
                            if tool.get("function", {}).get("name") == selected_cloud_name
                        ]
                        payload["tool_choice"] = {
                            "type": "function",
                            "function": {"name": selected_cloud_name},
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
        self.goal_state = None
        prompt_text = str(prompt)
        if "recover_command" in prompt_text.lower() and "expected postcondition" in prompt_text.lower():
            quoted = re.findall(r"`([^`]+)`", prompt_text)
            if len(quoted) >= 2:
                arguments = {
                    "command": quoted[0].strip(),
                    "expected": quoted[1].strip(),
                }
                tool_result = self.tool_handlers["recover_command"](**arguments)
                self.last_tool_calls.append({
                    "name": "recover_command",
                    "args": arguments,
                    "result": tool_result,
                })
                return str(tool_result)
        requested_tool = self._requested_local_tool(contents)
        # Resolve explicitly named generated capabilities from the live client
        # registry before any provider round-trip. This keeps execution local and
        # prevents provider-side argument generation from reinterpreting a repair
        # verification request.
        lower_prompt = prompt_text.lower()
        if re.search(r"\b(?:execute|run|use|verify|test)\b", lower_prompt) and re.search(r"\bcapabilit(?:y|ies)\b", lower_prompt):
            generated_names = []
            for name, handler in self.tool_handlers.items():
                if getattr(handler, "__nova_generated_capability__", False):
                    generated_names.append(name)
                    continue
                code = getattr(handler, "__code__", None)
                if code is not None and any(marker in code.co_names for marker in ("_run_android_mechanism_extension", "_run_extension_primitive")):
                    generated_names.append(name)
            for name in sorted(generated_names, key=len, reverse=True):
                if re.search(rf"\b{re.escape(name)}\b", lower_prompt):
                    requested_tool = name
                    break
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
        if requested_tool == "validate_android_mechanism":
            mechanism = self._extract_mechanism(prompt)
            if not mechanism:
                return "Mechanism validation requires an explicit mechanism such as intent:IMAGE_CAPTURE."
            return str(self.tool_handlers["validate_android_mechanism"](request=prompt, mechanism=mechanism))
        if requested_tool == "execute_validated_android_mechanism":
            mechanism = self._extract_mechanism(prompt)
            if not mechanism:
                try:
                    discovery = str(
                        self.tool_handlers["discover_android_mechanisms"](
                            request=prompt
                        )
                    )
                    candidates = self._rank_android_mechanism_candidates(
                        prompt,
                        self._parse_android_mechanism_candidates(discovery),
                    )
                    for candidate in candidates:
                        validation = str(
                            self.tool_handlers["validate_android_mechanism"](
                                request=prompt,
                                mechanism=candidate,
                            )
                        )
                        if "Status: VIABLE" in validation:
                            mechanism = candidate
                            break
                except (RuntimeError, ValueError, TypeError):
                    mechanism = ""
            if not mechanism:
                return (
                    "Mechanism execution could not select a viable discovered mechanism. "
                    "No Android mechanism was executed."
                )
            handler = self.tool_handlers.get("execute_android_mechanism")
            if handler is None:
                handler = self.tool_handlers["execute_validated_android_mechanism"]
            return str(
                handler(
                    request=prompt,
                    mechanism=mechanism,
                )
            )
        if requested_tool == "execute_validated_android_ui_mechanism":
            mechanism = self._extract_mechanism(prompt)
            if not mechanism:
                return "UI mechanism execution requires an explicit mechanism such as ui:<resource-id>."
            return str(execute_validated_android_ui_mechanism(request=prompt, mechanism=mechanism))
        if "expected postcondition" in prompt.lower() and "recover_command" in prompt.lower():
            command_match = re.search(r"`([^`]+)`", prompt)
            expected_match = re.search(
                r"expected postcondition(?:\s+is|\s*[:=])?\s*`([^`]+)`",
                prompt,
                re.IGNORECASE,
            )
            if command_match and expected_match:
                arguments = {
                    "command": command_match.group(1).strip(),
                    "expected": expected_match.group(1).strip(),
                }
                tool_result = self.tool_handlers["recover_command"](**arguments)
                self.last_tool_calls.append({
                    "name": "recover_command",
                    "args": arguments,
                    "result": tool_result,
                })
                return str(tool_result)
        return self._generate_cloudflare(contents, system_instruction)