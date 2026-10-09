"""Cloudflare Workers AI client for the minimal Nova agent."""

import json
import re
import os
from pathlib import Path
import urllib.error
import urllib.request
from collections.abc import Callable

from gemini_agent.android_ui import execute_validated_android_ui_mechanism
from gemini_agent.goal_state import GoalState, start_goal_state, is_premature_blocker_claim
from gemini_agent.goal_state_store import load_goal_state, save_goal_state
from gemini_agent.goal_progress import observe_goal_progress
from gemini_agent.goal_completion import verify_goal_completion
from gemini_agent.constructed_action import CONSTRUCTED_ACTION_DECLARATION
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
        self.provider = os.environ.get("NOVA_PROVIDER", "cloudflare").strip().lower()
        self.cloudflare_api_token = os.environ.get("CLOUDFLARE_API_TOKEN")
        self.cloudflare_account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        self.cloudflare_model = os.environ.get(
            "CLOUDFLARE_MODEL", "@cf/zai-org/glm-4.7-flash"
        )
        if self.provider == "openrouter":
            self.provider_api_token = os.environ.get("OPENROUTER_API_KEY")
            self.provider_model = os.environ.get("OPENROUTER_MODEL", "openrouter/free")
            self.provider_url = "https://openrouter.ai/api/v1/chat/completions"
            if not self.provider_api_token:
                raise RuntimeError(
                    "NOVA_PROVIDER=openrouter requires OPENROUTER_API_KEY."
                )
        elif self.provider == "groq":
            self.provider_api_token = os.environ.get("GROQ_API_KEY")
            self.provider_model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")
            self.provider_url = "https://api.groq.com/openai/v1/chat/completions"
            if not self.provider_api_token:
                raise RuntimeError("NOVA_PROVIDER=groq requires GROQ_API_KEY.")
        elif self.provider == "gemini":
            self.provider_api_token = os.environ.get("GEMINI_API_KEY")
            self.provider_model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
            self.provider_url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
            if not self.provider_api_token:
                raise RuntimeError("NOVA_PROVIDER=gemini requires GEMINI_API_KEY.")
        elif self.provider == "cloudflare":
            if not self.cloudflare_api_token or not self.cloudflare_account_id:
                raise RuntimeError(
                    "Configure CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID before starting the agent."
                )
            self.provider_api_token = self.cloudflare_api_token
            self.provider_model = self.cloudflare_model
            self.provider_url = (
                "https://api.cloudflare.com/client/v4/accounts/"
                f"{self.cloudflare_account_id}/ai/v1/chat/completions"
            )
        else:
            raise RuntimeError(
                "Unsupported NOVA_PROVIDER. Choose 'cloudflare', 'openrouter', 'groq', or 'gemini'."
            )
        self.tool_handlers = {**TOOL_HANDLERS, **(tool_handlers or {})}
        declarations = [*TOOL_DECLARATIONS, CONSTRUCTED_ACTION_DECLARATION, FIND_EXECUTABLE_DECLARATION, DIAGNOSE_COMMAND_FAILURE_DECLARATION, VERIFY_COMMAND_RESULT_DECLARATION, RETRY_COMMAND_DECLARATION, RUN_ROOT_COMMAND_DECLARATION, RUN_COMMAND_DECLARATION, LIST_PROCESSES_DECLARATION, GET_PROCESS_STATUS_DECLARATION, GET_PROCESS_COMMAND_LINE_DECLARATION, GET_PROCESS_EXECUTABLE_DECLARATION, GET_PROCESS_WORKING_DIRECTORY_DECLARATION, GET_PROCESS_PARENT_NAME_DECLARATION, GET_PROCESS_START_TIME_DECLARATION, GET_PROCESS_CPU_TIME_DECLARATION, GET_PROCESS_MEMORY_USAGE_DECLARATION, GET_PROCESS_NICE_DECLARATION, GET_NETWORK_ADDRESSES_DECLARATION, GET_SYSTEM_BATTERY_STATUS_DECLARATION, GET_SYSTEM_SCREEN_STATE_DECLARATION, GET_SYSTEM_SCREEN_TIMEOUT_DECLARATION, GET_SYSTEM_SCREEN_ORIENTATION_DECLARATION, GET_SYSTEM_SCREEN_RESOLUTION_DECLARATION, GET_SYSTEM_SCREEN_DENSITY_DECLARATION, GET_MEDIA_VOLUME_DECLARATION, GET_SYSTEM_SCREEN_REFRESH_RATE_DECLARATION, GET_SYSTEM_BOOT_TIME_DECLARATION, GET_SYSTEM_SWAP_USAGE_DECLARATION, GET_AIRPLANE_MODE_DECLARATION]
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

    def _persist_goal_state(self) -> None:
        if self.goal_state is not None:
            save_goal_state(self.goal_state)

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
    def _should_retry_with_auto_tool_choice(
        status: int, details: str, payload: dict, already_retried: bool = False
    ) -> bool:
        """Detect Cloudflare's malformed forced-tool argument parsing failure."""
        return (
            status == 400
            and not already_retried
            and isinstance(payload.get("tool_choice"), dict)
            and "Expecting value: line 1 column 1" in details
        )

    @staticmethod
    def _cloudflare_request_context(payload: dict, auto_tool_choice_retry_used: bool) -> dict:
        """Return safe, non-secret context for diagnosing provider request failures."""
        return {
            "model": payload.get("model"),
            "tool_choice": payload.get("tool_choice"),
            "tool_names": [
                tool.get("function", {}).get("name")
                for tool in payload.get("tools", [])
                if isinstance(tool, dict)
            ],
            "auto_tool_choice_retry_used": auto_tool_choice_retry_used,
        }

    @staticmethod
    def _tool_loop_exhaustion_diagnostic(
        max_rounds: int, tool_calls: list[dict], goal_state=None
    ) -> str:
        """Report bounded tool-call names after exhaustion without leaking tool output."""
        recent = [
            str(call.get("name", "unknown"))
            for call in tool_calls[-8:]
            if isinstance(call, dict)
        ]
        if recent:
            sequence = " -> ".join(recent)
            counts = {}
            for name in recent:
                counts[name] = counts.get(name, 0) + 1
            repeated = [f"{name} x{count}" for name, count in counts.items() if count > 1]
            repeated_note = (
                " Repeated tool names: " + ", ".join(repeated) + "."
                if repeated else ""
            )
        else:
            sequence = "none recorded"
            repeated_note = ""
        # Include only bounded, non-content execution context. The previous
        # name-only diagnostic could not distinguish repeated planning from repeated
        # writes, making a real execution loop impossible to diagnose.
        details = []
        for call in tool_calls[-8:]:
            if not isinstance(call, dict):
                continue
            name = str(call.get("name", "unknown"))
            result = str(call.get("result", ""))
            args = call.get("args") if isinstance(call.get("args"), dict) else {}
            if name == "select_goal_next_step":
                selected = re.search(r"Next step:\s*([A-Za-z_][A-Za-z0-9_]*)", result)
                if selected:
                    details.append(f"selector chose {selected.group(1)}")
            elif name == "write_text_file":
                path = args.get("path", args.get("file_path", "unknown"))
                outcome = "error" if re.search(r"\b(?:error|failed|failure)\b", result, re.I) else "returned"
                details.append(f"write_text_file path={str(path)[:120]} outcome={outcome}")
            elif name in {"acquire_termux_packages", "discover_dependency_options", "run_command", "execute_constructed_action", "verify_command_result"}:
                outcome = "error" if re.search(r"\b(?:error|failed|failure)\b", result, re.I) else "returned"
                details.append(f"{name} outcome={outcome}")
        detail_note = (" Recent safe details: " + " | ".join(details[-8:]) + ".") if details else ""
        status = getattr(goal_state, "status", None) or "no active runtime goal"
        return (
            f"Cloudflare requested too many tool calls ({max_rounds} rounds). "
            f"Recent registered tool sequence: {sequence}.{repeated_note} "
            f"Goal state: {status}.{detail_note} Tool contents and command output were omitted."
        )

    @staticmethod
    def _exclude_repeated_observation_tools(payload: dict, observations: list[dict]) -> bool:
        """Keep synthesis requests tool-capable while excluding tools that just stalled."""
        repeated_names = {
            str(item.get("name", ""))
            for item in observations
            if isinstance(item, dict) and item.get("name")
        }
        if not repeated_names:
            return False
        excluded_names = set(repeated_names)
        excluded_names.update(
            GeminiClient._CLOUD_TOOL_NAMES.get(name, name)
            for name in repeated_names
        )
        declared_tools = payload.get("tools")
        if not isinstance(declared_tools, list):
            return False
        remaining = [
            tool for tool in declared_tools
            if not (
                isinstance(tool, dict)
                and isinstance(tool.get("function"), dict)
                and tool["function"].get("name") in excluded_names
            )
        ]
        if not remaining:
            return False
        payload["tools"] = remaining
        payload["tool_choice"] = "auto"
        return len(remaining) != len(declared_tools)

    @staticmethod
    def _restore_tools_for_autonomous_goal(
        payload: dict, declarations: list[dict], autonomous_goal: bool
    ) -> bool:
        """Never send an active autonomous goal with no available tool declarations."""
        if not autonomous_goal or payload.get("tools"):
            return False
        payload["tools"] = [{
            "type": "function",
            "function": {
                "name": GeminiClient._CLOUD_TOOL_NAMES.get(
                    declaration.get("name", ""), declaration.get("name", "")
                ),
                "description": declaration.get("description", ""),
                "parameters": GeminiClient._schema(declaration.get("parameters", {})),
            },
        } for declaration in declarations if isinstance(declaration, dict)]
        if not payload["tools"]:
            return False
        # The goal runtime must retain the ability to take another bounded step.
        # Avoid stale forced choices after a previous tool was removed from the payload.
        payload["tool_choice"] = "auto"
        return True

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
    def _parse_text_tool_call(content, declarations: list[dict]) -> dict | None:
        """Convert an explicit provider text-tool envelope into a registered call."""
        if not isinstance(content, str) or "<tool_call>" not in content:
            return None
        match = re.search(
            r"<tool_call>\s*([A-Za-z_][A-Za-z0-9_]*)\b(.*?)(?:</tool_call>|$)",
            content,
            re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return None
        name = match.group(1)
        declaration = next(
            (item for item in declarations if isinstance(item, dict) and item.get("name") == name),
            None,
        )
        if declaration is None:
            return None
        parameters = declaration.get("parameters") or {}
        schema = parameters.get("properties") or {}
        body = match.group(2)
        args = {}
        matches = list(re.finditer(
            r"<arg_key>\s*(.*?)\s*</arg_key>\s*<arg_value>(.*?)</arg_value>",
            body,
            re.IGNORECASE | re.DOTALL,
        ))
        if not matches and re.search(r"<arg_key>\s*[^<]+</arg_key>", body, re.IGNORECASE):
            return None
        for arg_match in matches:
            key = arg_match.group(1).strip()
            if not key or key not in schema or key in args:
                return None
            value = arg_match.group(2).strip()
            value_type = schema[key].get("type") if isinstance(schema[key], dict) else None
            if value_type in {"object", "array", "number", "integer", "boolean", "null"}:
                try:
                    value = json.loads(value)
                except (TypeError, ValueError):
                    return None
            args[key] = value
        required = parameters.get("required") or []
        if any(key not in args for key in required):
            return None
        return {
            "id": "parsed-text-tool-call",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)},
        }
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

    def _recover_required_tool_arguments(
        self, local_name: str, args: dict, request_text: str
    ) -> dict:
        """Recover unambiguous required arguments from the active execution context."""
        recovered = dict(args)
        declaration = next(
            (
                item for item in self.tool_declarations
                if isinstance(item, dict) and item.get("name") == local_name
            ),
            None,
        )
        required = (
            (declaration or {}).get("parameters", {}).get("required", [])
            if declaration else []
        )
        for parameter in required:
            if str(recovered.get(parameter, "")).strip():
                continue
            if parameter == "request" and str(request_text).strip():
                recovered[parameter] = str(request_text).strip()
            elif parameter == "goal" and self.goal_state is not None:
                recovered[parameter] = self.goal_state.goal
            elif parameter == "success_condition" and self.goal_state is not None:
                recovered[parameter] = self.goal_state.success_condition
        return recovered

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
        # Explicit composition requests outrank every primitive mentioned as a
        # workflow step. Otherwise the first registered name (often calculator)
        # hijacks routing before the workflow-only declaration filter runs.
        if re.search(r"\brun_workflow\b", user_text):
            return "run_workflow"
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
            "execute a newly constructed workspace action",
            "execute a constructed workspace action",
            "execute_constructed_action",
        )):
            return "execute_constructed_action"

        if any(phrase in user_text for phrase in (
            "assess the autonomy boundary",
            "assess autonomy boundary",
            "decide whether to continue or escalate",
            "decide whether autonomous continuation is justified",
            "classify whether to stop, continue, investigate, recover, replan, or escalate",
        )):
            return "assess_autonomy_boundary"

        if any(phrase in user_text for phrase in (
            "build intent clarification",
            "clarify the intent contract",
            "generate clarification for the intent",
        )):
            return "build_intent_clarification"
        if any(phrase in user_text for phrase in (
            "represent entity relationships",
            "represent relationships between entities",
            "represent entity relationships and dependencies",
            "build an entity relationship representation",
            "create an entity relationship representation",
        )):
            return "represent_entity_relationships"
        if any(phrase in user_text for phrase in (
            "represent world evidence",
            "represent evidence and provenance",
            "represent evidence provenance",
            "build an evidence and provenance representation",
            "create an evidence and provenance representation",
        )):
            return "represent_world_evidence"

        if any(phrase in user_text for phrase in (
            "revise world beliefs",
            "revise beliefs",
            "update world beliefs",
            "revise the beliefs",
            "perform belief revision",
            "perform world belief revision",
        )):
            return "revise_world_beliefs"

        if any(phrase in user_text for phrase in (
            "query world model",
            "query the world model",
            "query internal world model",
            "search the world model",
            "ask the world model",
        )):
            return "query_world_model"

        if any(phrase in user_text for phrase in (
            "represent temporal states",
            "represent temporal state",
            "represent states over time",
            "represent entity history",
            "build a temporal state representation",
            "create a temporal state representation",
        )):
            return "represent_temporal_states"
        if any(phrase in user_text for phrase in (
            "represent entity states",
            "represent entities and their states",
            "represent entities with current states",
            "build an entity and state representation",
            "create an entity and state representation",
        )):
            return "represent_entity_states"

        if any(phrase in user_text for phrase in (
            "establish a goal portfolio",
            "establish goal portfolio",
            "create a goal portfolio",
            "represent multiple active goals",
        )):
            return "establish_goal_portfolio"
        if any(phrase in user_text for phrase in (
            "select goal priority",
            "select the goal priority",
            "choose which goal deserves attention",
            "choose the goal that deserves attention",
            "prioritize the active goals",
            "prioritize these goals",
        )):
            return "select_goal_priority"
        if any(phrase in user_text for phrase in (
            "resolve goal conflicts",
            "resolve the goal conflicts",
            "resolve conflicts between goals",
            "handle goal conflicts",
            "handle conflicts between goals",
        )):
            return "resolve_goal_conflicts"
        if any(phrase in user_text for phrase in (
            "verify goal portfolio",
            "verify the goal portfolio",
            "check goal portfolio coherence",
            "verify portfolio coherence",
        )):
            return "verify_goal_portfolio"

        if any(phrase in user_text for phrase in (
            "manage goal interruption",
            "pause and resume a goal",
            "pause the goal and resume it",
            "interrupt and resume the goal",
            "pause this goal",
        )):
            return "manage_goal_interruption"
        if any(phrase in user_text for phrase in (
            "establish an intent contract",
            "establish intent contract",
            "intent contract",
            "interpret my request as a bounded intent",
        )):
            return "establish_intent_contract"
        if any(phrase in user_text for phrase in (
            "select the goal next step",
            "select a goal next step",
            "choose the next step for the goal",
            "choose a goal-directed next step",
        )):
            return "select_goal_next_step"
        if any(phrase in user_text for phrase in (
            "diagnose outcome discrepancy",
            "diagnose the outcome discrepancy",
            "diagnose the outcome mismatch",
            "determine whether reality matches the expected outcome",
            "decide whether to stop or replan from observed outcome",
        )):
            return "diagnose_outcome_discrepancy"
        if any(phrase in user_text for phrase in (
            "verify the outcome against the contract",
            "verify outcome against the contract",
            "verify the outcome contract",
            "verify outcome evidence",
            "check whether the outcome was actually achieved",
        )):
            return "verify_outcome_contract"
        if any(phrase in user_text for phrase in (
            "establish an outcome contract",
            "establish outcome contract",
            "define the outcome contract",
            "define an outcome contract",
            "set the outcome contract",
        )):
            return "establish_outcome_contract"
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

        if any(phrase in user_text for phrase in (
            "select capability by evidence",
            "select the best capability by evidence",
            "choose capability by evidence",
            "evidence-aware capability selection",
        )):
            return "select_capability_by_evidence"
        if any(phrase in user_text for phrase in (
            "assess capability evidence quality",
            "capability evidence quality",
            "evidence quality for capability",
            "is the capability evidence sufficient",
            "is the capability verification evidence sufficient",
            "check capability evidence freshness",
            "check capability verification evidence",
        )):
            return "assess_capability_evidence_quality"
        if any(phrase in user_text for phrase in (
            "assess capability evidence provenance",
            "capability evidence provenance",
            "evidence provenance for capability",
            "is the capability evidence directly tied",
            "is the capability verification evidence directly tied",
            "check capability evidence provenance",
            "check capability verification provenance",
        )):
            return "assess_capability_evidence_provenance"
        if any(phrase in user_text for phrase in (
            "assess your own readiness",
            "assess capability readiness",
            "capability readiness",
            "which capabilities are verified",
            "which capabilities are unverified",
            "capabilities are actually available",
            "capabilities are merely present",
            "capability evidence and persisted verification history",
        )):
            return "assess_capability_readiness"
        if "capability inventory" in user_text or "capabilities" in user_text or "what tools" in user_text:
            return "capability_inventory"
        if "assess_capability_gap" in user_text:
            return "assess_capability_gap"
        if "discover executable resources" in user_text or "discover_workspace_executables" in user_text:
            return "discover_workspace_executables"
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
            # Broad software-construction goals need workspace, execution, and
            # verification tools, not the entire Android diagnostics catalog.
            "construction": (
                "create an app", "build an app", "create a minimal android",
                "new workspace", "from scratch", "software project",
                "build procedure", "source files", "construct a project",
                "apk", "install necessary packages", "dependency acquisition",
                "discover dependency options", "arithmetic testing",
                "continue through building", "build strategy",
            ),
            "workflow": ("workflow", "compose capabilities", "multi-step sequence"),
        }

        # An explicit workflow-tool request must not expose atomic tools alongside
        # the workflow orchestrator. Otherwise the model can bypass composition and
        # execute the first primitive directly, even when workflow registration works.
        if re.search(r"\brun_workflow\b", user_text):
            return [
                declaration for declaration in self.tool_declarations
                if declaration.get("name") == "run_workflow"
            ]

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
                or (selected_groups & {"construction"} and name in {
                    "run_command", "find_executable", "discover_workspace_executables",
                    "discover_dependency_options", "acquire_termux_packages",
                    "execute_constructed_action",
                    "verify_command_result", "diagnose_command_failure",
                    "retry_command", "recover_command", "capability_inventory",
                    "assess_capability_gap",
                    "path_exists", "create_directory", "delete_directory", "get_file_info",
                    "get_file_extension", "get_file_name", "get_file_stem", "get_file_parent",
                    "list_directory_recursive", "move_directory", "copy_directory", "hash_file",
                    "count_file_lines", "get_directory_entry_count", "get_disk_usage",
                    "get_directory_size", "list_directory", "read_text_file", "search_text",
                    "write_text_file", "edit_text_file", "append_text_file", "copy_file",
                    "move_file", "delete_file", "find_files",
                })
                or (selected_groups & {"calculator"} and name == "calculator")
                or (selected_groups & {"current_datetime"} and name == "current_datetime")
                or (selected_groups & {"workflow"} and name == "run_workflow")
            ):
                selected_names.add(name)

        # Saved workflow discovery is relevant only when the user asks about
        # workflow selection/reuse. Keep it available alongside atomic tools for
        # mixed goals, without leaking it into unrelated narrow routes.
        if "workflow" in selected_groups:
            selected_names.update({"list_saved_workflows", "run_saved_workflow"})

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


    @staticmethod
    def _should_return_tool_result_directly(
        requested_tool: str | None, loop_index: int
    ) -> bool:
        """Keep explicit bounded local-tool requests from being reinterpreted by the provider."""
        direct_tools = {
            "capability_inventory", "assess_capability_gap", "plan_capability_extension",
            "self_test", "discover_camera_control", "resolve_android_intent",
            "send_android_keyevent", "send_android_intent", "list_processes",
            "run_root_command", "run_command", "find_executable",
            "discover_workspace_executables", "diagnose_command_failure",
            "verify_command_result", "retry_command", "recover_command",
            "path_exists", "get_file_access_time", "get_file_modified_time",
            "get_file_extension", "get_file_name", "get_file_stem",
            "get_file_permissions", "get_directory_entry_count", "get_directory_size",
            "count_file_lines", "get_disk_usage", "get_hostname", "get_system_info",
            "get_cpu_count", "get_process_id", "get_current_working_directory",
            "get_python_executable", "get_memory_usage", "get_temp_directory",
            "get_home_directory", "get_process_uptime", "get_process_thread_count",
            "get_parent_process_id", "get_process_group_id", "get_session_id",
            "get_user_id", "get_umask", "get_process_status",
            "get_process_command_line", "get_process_executable",
            "get_process_working_directory", "get_process_parent_name",
            "get_process_memory_usage", "get_system_uptime", "get_system_swap_usage",
            "get_system_boot_time", "get_system_cpu_usage", "get_system_battery_status",
            "get_wifi_status", "get_bluetooth_status", "get_airplane_mode",
            "get_screen_state", "get_screen_brightness", "get_screen_brightness_mode",
            "get_screen_resolution", "get_screen_density", "get_media_volume",
            "get_screen_refresh_rate", "get_screen_timeout",
        }
        return loop_index == 0 and requested_tool in direct_tools

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
        goal_replan_notes: list[str] = []
        goal_replan_step = ""

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
            "mechanism/capability and independently verify execution. "
            "Adaptive investigation rule: an unavailable, blocked, failed, or inconclusive "
            "observation mechanism is evidence about that mechanism, not evidence that the "
            "requested fact is unknowable. When a required fact remains unknown, identify "
            "and try a distinct already-registered mechanism capable of observing the same "
            "fact, while preserving read-only and safety constraints. Do not stop merely "
            "because the first diagnostic path is blocked. Stop only after the fact is "
            "verified, the remaining uncertainty is explicitly justified, or the available "
            "mechanisms have been meaningfully exhausted."
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
            if normal_request_match:                goal = normal_request_match.group(1).strip()
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
        # Keep intent interpretation deterministic and provider-independent.
        if requested_tool == "build_intent_clarification":
            match = re.search(
                r'build\s+intent\s+clarification\s+for\s+"([^"]+)".*?uncertainty\s+is\s+"([^"]+)".*?required\s+evidence\s+is\s+"([^"]+)".*?clarification\s+is\s+"([^"]+)"',
                request_text,
                re.IGNORECASE,
            )
            if match:
                args = {
                    "request": match.group(1),
                    "uncertainty": match.group(2),
                    "required_evidence": match.group(3),
                    "clarification_required": match.group(4),
                }
                result = self.tool_handlers["build_intent_clarification"](**args)
                self.last_tool_calls.append({
                    "name": "build_intent_clarification",
                    "args": args,
                    "result": result,
                })
                return result
        if requested_tool == "select_goal_priority":
            match = re.search(
                r'(?:select|choose)\s+(?:the\s+)?(?:goal\s+)?priority(?:\s+from)?\s*:?\s*"([^"]+)"',
                request_text,
                re.IGNORECASE | re.DOTALL,
            )
            if not match:
                match = re.search(
                    r'(?:select|choose)\s+(?:which\s+)?goal(?:\s+deserves\s+attention)?(?:\s+from)?\s*:?\s*"([^"]+)"',
                    request_text,
                    re.IGNORECASE | re.DOTALL,
                )
            if match:
                args = {"goals": match.group(1).replace("\\n", "\n")}
                result = self.tool_handlers["select_goal_priority"](**args)
                self.last_tool_calls.append({"name": "select_goal_priority", "args": args, "result": result})
                return result
            return "Selecting goal priority requires one or more goal entries using: goal_id | goal | urgency | user_priority | dependency_count | resource_cost"
        if requested_tool == "resolve_goal_conflicts":
            match = re.search(
                r'(?:resolve\s+(?:the\s+)?goal\s+conflicts|resolve\s+conflicts\s+between\s+goals|handle\s+(?:the\s+)?goal\s+conflicts|handle\s+conflicts\s+between\s+goals)(?:\s+from|\s+with)?\s*:?\s*"([^"]+)"',
                request_text,
                re.IGNORECASE | re.DOTALL,
            )
            if match:
                args = {"goals": match.group(1).replace("\\n", "\n")}
                result = self.tool_handlers["resolve_goal_conflicts"](**args)
                self.last_tool_calls.append({"name": "resolve_goal_conflicts", "args": args, "result": result})
                return result
            return "Resolving goal conflicts requires one or more goal entries using: goal_id | goal | conflict_key | constraint"

        if requested_tool == "query_world_model":
            fields = {}
            patterns = {
                "entities": r'(?:entities|entity\s+states?)\s*(?:are|is|:|using|from|with)?\s*"([^"]*)"',
                "relationships": r'(?:relationships|relations)\s*(?:are|is|:|using|from|with)?\s*"([^"]*)"',
                "evidence": r'(?:evidence|evidence\s+records?)\s*(?:are|is|:|using|from|with)?\s*"([^"]*)"',
                "temporal_states": r'(?:temporal\s+states|temporal\s+observations|observations)\s*(?:are|is|:|using|from|with)?\s*"([^"]*)"',
                "beliefs": r'(?:beliefs|belief\s+records?)\s*(?:are|is|:|using|from|with)?\s*"([^"]*)"',
                "query": r'(?:query|question|fact\s+to\s+find)\s*(?:is|:|about|for)?\s*"([^"]+)"',
            }
            for key, pattern in patterns.items():
                match = re.search(pattern, request_text, re.IGNORECASE | re.DOTALL)
                if match:
                    fields[key] = match.group(1).replace("\\n", "\n")
            if all(key in fields for key in patterns):
                result = self.tool_handlers["query_world_model"](**fields)
                self.last_tool_calls.append({"name": "query_world_model", "args": fields, "result": result})
                return result
            return (
                "World-model query requires entities, relationships, evidence, temporal states, "
                "beliefs, and a query, each supplied in quotes. Use an empty string for an unused "
                "record category."
            )

        if requested_tool == "revise_world_beliefs":
            entities_match = re.search(
                r'(?:entities|entity\s+states?)\s*(?:are|is|:|using|from|with)?\s*"([^"]+)"',
                request_text,
                re.IGNORECASE | re.DOTALL,
            )
            beliefs_match = re.search(
                r'(?:beliefs|belief\s+records?)\s*(?:are|is|:|using|from|with)?\s*"([^"]+)"',
                request_text,
                re.IGNORECASE | re.DOTALL,
            )
            evidence_match = re.search(
                r'(?:evidence|revision\s+evidence)\s*(?:are|is|:|using|from|with)?\s*"([^"]+)"',
                request_text,
                re.IGNORECASE | re.DOTALL,
            )
            if entities_match and beliefs_match and evidence_match:
                args = {
                    "entities": entities_match.group(1).replace("\\n", "\n"),
                    "beliefs": beliefs_match.group(1).replace("\\n", "\n"),
                    "evidence": evidence_match.group(1).replace("\\n", "\n"),
                }
                result = self.tool_handlers["revise_world_beliefs"](**args)
                self.last_tool_calls.append({"name": "revise_world_beliefs", "args": args, "result": result})
                return result
            return (
                "Belief revision requires entities using: entity_id | entity_type | state | confidence; "
                "beliefs using: entity_id | claim | confidence; and evidence using: "
                "entity_id | claim | source | confidence | SUPPORTS or CONTRADICTS"
            )

        if requested_tool == "represent_temporal_states":
            entities_match = re.search(
                r'(?:entities|entity\s+states?)\s*(?:are|is|:|using|from|with)?\s*"([^"]+)"',
                request_text,
                re.IGNORECASE | re.DOTALL,
            )
            observations_match = re.search(
                r'(?:observations|temporal\s+observations|states\s+over\s+time)\s*(?:are|is|:|using|from|with)?\s*"([^"]+)"',
                request_text,
                re.IGNORECASE | re.DOTALL,
            )
            if entities_match and observations_match:
                args = {
                    "entities": entities_match.group(1).replace("\\n", "\n"),
                    "observations": observations_match.group(1).replace("\\n", "\n"),
                }
                result = self.tool_handlers["represent_temporal_states"](**args)
                self.last_tool_calls.append({"name": "represent_temporal_states", "args": args, "result": result})
                return result
            return (
                "Representing temporal states requires entities using: "
                "entity_id | entity_type | state | confidence; and observations using: "
                "entity_id | state | observed_at | confidence"
            )

        if requested_tool == "represent_entity_states":
            match = re.search(
                r'(?:represent\s+(?:the\s+)?entities?(?:\s+and\s+their\s+states)?|represent\s+entity\s+states|build\s+an\s+entity\s+and\s+state\s+representation|create\s+an\s+entity\s+and\s+state\s+representation)(?:\s+from|\s+using|\s+with)?\s*:?\s*"([^"]+)"',
                request_text,
                re.IGNORECASE | re.DOTALL,
            )
            if match:
                args = {"entities": match.group(1).replace("\\n", "\n")}
                result = self.tool_handlers["represent_entity_states"](**args)
                self.last_tool_calls.append({"name": "represent_entity_states", "args": args, "result": result})
                return result
            return "Representing entity states requires one or more entries using: entity_id | entity_type | state | confidence"

        if requested_tool == "represent_entity_relationships":
            entities_match = re.search(
                r'(?:entities|entity\s+states?)\s*(?:are|is|:|using|from|with)?\s*"([^"]+)"',
                request_text,
                re.IGNORECASE | re.DOTALL,
            )
            relationships_match = re.search(
                r'(?:relationships|relations)\s*(?:are|is|:|using|from|with)?\s*"([^"]+)"',
                request_text,
                re.IGNORECASE | re.DOTALL,
            )
            if entities_match and relationships_match:
                args = {
                    "entities": entities_match.group(1).replace("\\n", "\n"),
                    "relationships": relationships_match.group(1).replace("\\n", "\n"),
                }
                result = self.tool_handlers["represent_entity_relationships"](**args)
                self.last_tool_calls.append({"name": "represent_entity_relationships", "args": args, "result": result})
                return result
            return (
                "Representing entity relationships requires entities using: "
                "entity_id | entity_type | state | confidence; and relationships using: "
                "source_entity_id | relationship | target_entity_id"
            )

        if requested_tool == "represent_world_evidence":
            entities_match = re.search(
                r'(?:entities|entity\s+states?)\s*(?:are|is|:|using|from|with)?\s*"([^"]+)"',
                request_text,
                re.IGNORECASE | re.DOTALL,
            )
            evidence_match = re.search(
                r'(?:evidence|evidence\s+records?)\s*(?:are|is|:|using|from|with)?\s*"([^"]+)"',
                request_text,
                re.IGNORECASE | re.DOTALL,
            )
            if entities_match and evidence_match:
                args = {
                    "entities": entities_match.group(1).replace("\\n", "\n"),
                    "evidence": evidence_match.group(1).replace("\\n", "\n"),
                }
                result = self.tool_handlers["represent_world_evidence"](**args)
                self.last_tool_calls.append({"name": "represent_world_evidence", "args": args, "result": result})
                return result
            return (
                "Representing world evidence requires entities using: "
                "entity_id | entity_type | state | confidence; and evidence using: "
                "entity_id | claim | source | confidence"
            )

        if requested_tool == "verify_goal_portfolio":
            expected_match = re.search(
                r'(?:expected\s+goal\s+ids|expected\s+ids)\s*(?:are|is|:)?\s*"([^"]+)"',
                request_text,
                re.IGNORECASE | re.DOTALL,
            )
            goals_match = re.search(
                r'(?:and\s+)?(?:the\s+)?goals?\s*(?:are|is|:|using|from)?\s*"([^"]+)"',
                request_text,
                re.IGNORECASE | re.DOTALL,
            )
            if expected_match and goals_match:
                args = {
                    "expected_goal_ids": expected_match.group(1).strip(),
                    "goals": goals_match.group(1).replace("\\n", "\n"),
                }
                result = self.tool_handlers["verify_goal_portfolio"](**args)
                self.last_tool_calls.append({"name": "verify_goal_portfolio", "args": args, "result": result})
                return result
            return "Verifying a goal portfolio requires expected goal ids and goals using: goal_id | goal | success_condition | status | evidence"

        if requested_tool == "manage_goal_interruption":
            match = re.search(
                r'(?:manage\s+goal\s+interruption|pause\s+(?:and\s+resume\s+)?(?:the\s+)?goal(?:\s+and\s+resume\s+it)?)\s+(?:for|with)?\s*:?\s*"([^"]+)"',
                request_text,
                re.IGNORECASE | re.DOTALL,
            )
            if match:
                args = {"goal": match.group(1).replace("\\n", "\n")}
                result = self.tool_handlers["manage_goal_interruption"](**args)
                self.last_tool_calls.append({"name": "manage_goal_interruption", "args": args, "result": result})
                return result
            return "Managing goal interruption requires: goal_id | status | checkpoint | action[, action...]"

        if requested_tool == "establish_goal_portfolio":
            match = re.search(
                r'establish\s+(?:a\s+)?goal\s+portfolio(?:\s+with)?\s*:\s*"([^"]+)"',
                request_text,
                re.IGNORECASE | re.DOTALL,
            )
            if not match:
                match = re.search(
                    r'(?:establish|create)\s+(?:a\s+)?goal\s+portfolio(?:\s+with)?\s+"([^"]+)"',
                    request_text,
                    re.IGNORECASE | re.DOTALL,
                )
            if match:
                args = {"goals": match.group(1).replace("\\n", "\n")}
                result = self.tool_handlers["establish_goal_portfolio"](**args)
                self.last_tool_calls.append({"name": "establish_goal_portfolio", "args": args, "result": result})
                return result
            return "Establishing a goal portfolio requires one or more goal entries using: goal_id | goal | success_condition"
        if requested_tool == "establish_intent_contract":
            match = re.search(
                r'\bestablish\s+(?:an\s+)?intent\s+contract\s+for\s+"([^"]+)"',
                request_text,
                re.IGNORECASE,
            )
            if match:
                result = self.tool_handlers["establish_intent_contract"](request=match.group(1))
                self.last_tool_calls.append({
                    "name": "establish_intent_contract",
                    "args": {"request": match.group(1)},
                    "result": result,
                })
                return result
        # Keep the goal-contract safety boundary deterministic even if local
        # routing heuristics do not recognize the phrasing of this explicit request.
        if (
            not requested_tool
            and re.search(r"\bestablish\s+(?:a\s+)?goal\s+contract\b", request_text, re.IGNORECASE)
        ):
            requested_tool = "establish_goal_contract"
        # A compound strategy-selection workflow must stay in the normal decision
        # loop. Do not let a nested strategy name such as verify_command_result
        # hijack the whole request into a single local verifier call.
        if requested_tool == "assess_autonomy_boundary":
            patterns = {
                "goal": r'\b(?:the )?goal\s+"([^"]+)"',
                "outcome_state": r'\boutcome state\s*(?:is|was|[:=])?\s*"?(ACHIEVED|VERIFIED|COMPLETE|COMPLETED|MISMATCH|FAILED|CONTRADICTED|PARTIAL_OR_UNCERTAIN|INCONCLUSIVE|MISMATCH_OR_UNKNOWN|UNKNOWN|UNKNOWN_MISMATCH)"?',
                "uncertainty": r'\buncertainty\s*(?:is|was|:)?\s*"([^"]+)"',
                "observed_evidence": r'\b(?:observed evidence|supplied observed evidence)\s*(?:is|was|:)?\s*"([^"]+)"',
                "available_actions": r'\bavailable actions\s*(?:are|is|were|:)?\s*"([^"]+)"',
                "risk_constraints": r'\brisk constraints\s*(?:are|is|were|:)?\s*"([^"]+)"',
            }
            extracted = {}
            for key, pattern in patterns.items():
                match = re.search(pattern, prompt, re.IGNORECASE | re.DOTALL)
                if match:
                    extracted[key] = match.group(1).strip() if key != "outcome_state" else match.group(1).upper()
            required = tuple(patterns)
            if all(key in extracted for key in required):
                result = str(self.tool_handlers[requested_tool](**extracted))
                self.last_tool_calls.append({"name": requested_tool, "args": extracted, "result": result})
                return result
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
            self._persist_goal_state()
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
            autonomous_pursuit = bool(
                re.search(
                    r"\b(?:pursue|continue|work\s+toward|achieve)\b.*\b(?:goal|autonomously|automatically)\b|\bautonomously\b",
                    request_text,
                    re.IGNORECASE | re.DOTALL,
                )
            )
            continuation = re.search(r"\b(?:then|after that|next)\b", request_text, re.IGNORECASE)
            if autonomous_pursuit:
                # In autonomous goals, words such as "then" may occur inside the
                # quoted goal/success condition. Do not mistake that natural-language
                # ordering for an explicit local tool request; the goal bridge owns
                # step selection.
                requested_tool = None
            elif not continuation:
                if not autonomous_pursuit:
                    return result
                requested_tool = None
            else:
                continuation_text = request_text[continuation.end():].strip()
                continuation_contents = [{"role": "user", "parts": [{"text": continuation_text}]}]
                next_tool = self._requested_local_tool(continuation_contents)
                if not next_tool:
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
                    step_status = (
                        "VERIFIED" if completion.status == "VERIFIED"
                        else "FAILED" if completion.status == "FAILED"
                        else "EXECUTED"
                    )
                    self.goal_state.record_step(
                        requested_tool, step_status, continuation_result
                    )
                    self._persist_goal_state()
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
        if (
            self.goal_state is not None
            and not requested_tool
            and not strategy_candidates
            and re.search(
                r"\b(?:pursue|continue|work\s+toward|achieve)\b.*\b(?:goal|autonomously|automatically)\b|\bautonomously\b",
                request_text,
                re.IGNORECASE | re.DOTALL,
            )
        ):
            # Long-horizon goal selection must see the full registered action set.
            # Relevance filtering can hide a prerequisite action whose name is not
            # lexically identical to the success-condition wording.
            goal_declarations = self.tool_declarations
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
                    "\n".join(self.goal_state.evidence),
                )
                if goal_selection.action == "STOP":
                    return (
                        "Goal-directed next step: STOP\\n"
                        f"Reason: {goal_selection.reason}\\n"
                        "No goal-directed action was executed."
                    )
                if (
                    goal_selection.action in self.tool_handlers
                    and any(
                        declaration.get("name") == goal_selection.action
                        for declaration in self.tool_declarations
                    )
                ):
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

        if requested_tool == "execute_constructed_action":
            patterns = {
                "executable": r"executable\s*[:=]\s*([^,\n]+)",
                "arguments": r"arguments\s*[:=]\s*(\[[^\]]*\])",
                "working_directory": r"working_directory\s*[:=]\s*([^,\n]+)",
                "timeout_seconds": r"timeout_seconds\s*[:=]\s*(\d+)",
                "mutation_scope": r"mutation_scope\s*[:=]\s*([^,\n]+)",
                "expected_effects": r"expected_effects\s*[:=]\s*(\[[^\]]*\])",
                "evidence_requirements": r"evidence_requirements\s*[:=]\s*(\[[^\]]*\])",
            }
            fields = {}
            for key, pattern in patterns.items():
                match = re.search(pattern, request_text, re.IGNORECASE)
                if match:
                    fields[key] = match.group(1).strip().rstrip(";,")
            if len(fields) == len(patterns):
                try:
                    arguments = json.loads(fields["arguments"])
                    expected_effects = json.loads(fields["expected_effects"])
                    evidence_requirements = json.loads(fields["evidence_requirements"])
                    args = {
                        "executable": fields["executable"].strip().strip(chr(96)).strip(),
                        "arguments": arguments,
                        "working_directory": fields["working_directory"].strip().strip(chr(96)).strip(),
                        "timeout_seconds": int(fields["timeout_seconds"]),
                        "mutation_scope": fields["mutation_scope"].strip().strip(chr(96)).strip(),
                        "expected_effects": expected_effects,
                        "evidence_requirements": evidence_requirements,
                    }
                    result = str(self.tool_handlers["execute_constructed_action"](**args))
                    self.last_tool_calls.append({"name": "execute_constructed_action", "args": args, "result": result})
                    return result
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    return f"Constructed action request rejected: {exc}"
        if requested_tool == "execute_constructed_action":
            patterns = {
                "executable": r"executable\s*[:=]\s*([^,\n]+)",
                "arguments": r"arguments\s*[:=]\s*(\[[^\n]+\])",
                "working_directory": r"working_directory\s*[:=]\s*([^,\n]+)",
                "timeout_seconds": r"timeout_seconds\s*[:=]\s*(\d+)",
                "mutation_scope": r"mutation_scope\s*[:=]\s*([^,\n]+)",
                "expected_effects": r"expected_effects\s*[:=]\s*(\[[^\n]+\])",
                "evidence_requirements": r"evidence_requirements\s*[:=]\s*(\[[^\n]+\])",
            }
            fields = {}
            for key, pattern in patterns.items():
                match = re.search(pattern, prompt_text, re.IGNORECASE)
                if match: fields[key] = match.group(1).strip().rstrip(";,")
            if len(fields) == len(patterns):
                try:
                    args = {
                        "executable": fields["executable"].strip().strip(chr(96)).strip(),
                        "arguments": json.loads(fields["arguments"]),
                        "working_directory": fields["working_directory"].strip().strip(chr(96)).strip(),
                        "timeout_seconds": int(fields["timeout_seconds"]),
                        "mutation_scope": fields["mutation_scope"].strip().strip(chr(96)).strip(),
                        "expected_effects": json.loads(fields["expected_effects"]),
                        "evidence_requirements": json.loads(fields["evidence_requirements"]),
                    }
                    result = str(self.tool_handlers["execute_constructed_action"](**args))
                    self.last_tool_calls.append({"name":"execute_constructed_action","args":args,"result":result})
                    return result
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    return f"Constructed action request rejected: {exc}"
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
        if requested_tool == "diagnose_outcome_discrepancy":
            patterns = {
                "goal": r'\b(?:the )?goal\s+"([^"]+)"',
                "success_condition": r'\bsuccess condition (?:was|is)\s+"([^"]+)"',
                "expected_transition": r'\bexpected transition (?:was|is)\s+"([^"]+)"',
                "failure_condition": r'\bfailure condition (?:was|is)\s+"([^"]+)"',
                "observed_evidence": r'\b(?:supplied )?observed evidence (?:is|was)\s+"([^"]+)"',
            }
            extracted = {}
            for key, pattern in patterns.items():
                match = re.search(pattern, prompt, re.IGNORECASE | re.DOTALL)
                if match:
                    extracted[key] = match.group(1).strip()
            required = tuple(patterns)
            if all(key in extracted for key in required):
                return str(self.tool_handlers["diagnose_outcome_discrepancy"](**extracted))
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
            "model": self.provider_model,
            "messages": messages,
            "max_completion_tokens": 2048,
            "tools": tools,
            # Serialize tool execution so unfamiliar investigations grow through
            # verified observations instead of parallel tool-call bursts that
            # Cloudflare may reject as excessive.
            "parallel_tool_calls": False,
        }
        if requested_tool == "apply_capability_extension":
            payload["tool_choice"] = {
                "type": "function",
                "function": {"name": "apply_capability_extension"},
            }
        elif goal_selected_action:
            selected_cloud_name = self._CLOUD_TOOL_NAMES.get(
                goal_selected_action, goal_selected_action            )
            selected_declaration = next(                (
                    declaration
                    for declaration in self.tool_declarations
                    if isinstance(declaration, dict)
                    and declaration.get("name") == goal_selected_action
                ),
                None,
            )
            selected_required = (
                selected_declaration.get("parameters", {}).get("required", [])
                if selected_declaration
                else []
            )
            # An active goal must execute its selected action, not permit a
            # prose-only response to masquerade as progress. Function forcing still
            # lets the provider generate arguments for tools that require them.
            payload["tools"] = [
                tool
                for tool in payload.get("tools", [])
                if tool.get("function", {}).get("name") == selected_cloud_name
            ]
            payload["tool_choice"] = {
                "type": "function",
                "function": {"name": selected_cloud_name},
            }
        elif strategy_candidates and selected_strategy:
            selected_cloud_name = self._CLOUD_TOOL_NAMES.get(selected_strategy, selected_strategy)
            payload["tool_choice"] = {
                "type": "function",
                "function": {"name": selected_cloud_name},
            }
        elif requested_tool:
            cloud_requested_name = self._CLOUD_TOOL_NAMES.get(requested_tool, requested_tool)
            if cloud_requested_name == "run_root_command":
                payload["tool_choice"] = "auto"
            else:
                payload["tool_choice"] = {
                    "type": "function",
                    "function": {"name": cloud_requested_name},
                }
        elif self._requires_local_tool(contents):
            payload["tool_choice"] = "required"

        url = self.provider_url

        # Final autonomous-goal guard: root diagnostic commands require provider-generated
        # arguments, so never let an earlier routing branch replace the non-forced choice.
        autonomous_goal = bool(
            self.goal_state is not None
            and re.search(r"\bautonomously\b", request_text, re.IGNORECASE)
        )
        if autonomous_goal and any(
            tool.get("function", {}).get("name") == "run_root_command"
            for tool in payload.get("tools", [])
        ):
            payload["tool_choice"] = "auto"

        # Long-horizon investigation may require more than three distinct observations.
        # Keep the budget bounded, but do not force unfamiliar tasks into a three-step shape.
        # Adaptive investigations may need several distinct observations before
        # the model can establish a reliable environment picture. Keep a
        # generous finite ceiling while relying on the loop's natural stop
        # condition when the model has enough evidence.
        max_tool_rounds = 16
        provider_tool_choice_retry_used = False
        last_observation_signature = None
        goal_blocker_rejections = 0
        malformed_text_tool_retries = set()
        for loop_index in range(max_tool_rounds):
            round_trace_start = len(self.last_tool_calls)
            # Some recovery/strategy branches intentionally remove tools after a
            # bounded action. For an active autonomous goal, restore the relevant
            # tool profile before the next provider round instead of sending a
            # contradictory tool-less continuation request.
            self._restore_tools_for_autonomous_goal(
                payload,
                self._relevant_tool_declarations(contents),
                autonomous_goal,
            )
            request = urllib.request.Request(
                url,
                data=json.dumps(payload).encode(),
                headers={
                    "Authorization": f"Bearer {self.provider_api_token}",
                    "Content-Type": "application/json",
                    **(
                        {"HTTP-Referer": "https://github.com/Hausshehe/nova-agent", "X-Title": "Nova Agent"}
                        if self.provider == "openrouter" else {}
                    ),
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
                if self._should_retry_with_auto_tool_choice(
                    exc.code, details, payload, provider_tool_choice_retry_used
                ):
                    # Cloudflare can fail while parsing arguments for a forced
                    # function call before returning a completion. Retry once with
                    # automatic choice, keeping the selected tool declaration bounded.
                    provider_tool_choice_retry_used = True
                    payload["tool_choice"] = "auto"
                    continue
                request_context = self._cloudflare_request_context(
                    payload, provider_tool_choice_retry_used
                )
                raise RuntimeError(
                    f"{self.provider.title()} API error ({exc.code}): {details}; "
                    "request context: " + json.dumps(request_context, sort_keys=True)
                ) from exc
            except TimeoutError as exc:
                raise RuntimeError(
                    f"{self.provider.title()} request timed out while waiting for the model response."
                ) from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(
                    f"Could not reach {self.provider.title()}: {exc.reason}"
                ) from exc
            except OSError as exc:
                # Socket-level failures such as ConnectionAbortedError are not
                # consistently wrapped in URLError by urllib.
                raise RuntimeError(
                    f"Connection to {self.provider.title()} failed: {exc}"
                ) from exc

            try:
                message = result["choices"][0]["message"]
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError(
                    f"Cloudflare returned an unexpected response: {result}"
                ) from exc

            tool_calls = message.get("tool_calls") or []
            native_tool_calls = bool(tool_calls)

            # Some compatible endpoints emit structured tool calls as text
            # rather than message.tool_calls. Accept only an explicit envelope
            # and only names and argument keys registered by this runtime.
            if not tool_calls:
                text_call = self._parse_text_tool_call(
                    message.get("content", ""),
                    self.tool_declarations,
                )
                if text_call is not None:
                    tool_calls = [text_call]
                    native_tool_calls = False

            if not tool_calls:
                # Some providers acknowledge a forced continuation tool in
                # reasoning but omit the actual tool call. When Nova itself
                # selected a bounded no-argument tool, execute that selected
                # action locally rather than losing the autonomous step.
                forced = payload.get("tool_choice")
                forced_cloud_name = ""
                if (
                    self.goal_state is not None
                    and self.goal_state.status == "ACTIVE"
                    and isinstance(forced, dict)
                    and forced.get("type") == "function"
                ):
                    forced_cloud_name = str(
                        forced.get("function", {}).get("name", "")
                    ).strip()

                # Do not depend on the provider echoing Nova's tool_choice back
                # correctly. The local continuation decision is already recorded
                # in the trace, so it is authoritative for this bounded step.
                if (
                    self.goal_state is not None
                    and self.goal_state.status == "ACTIVE"
                    and not forced_cloud_name
                ):
                    for trace in reversed(self.last_tool_calls):
                        if trace.get("name") == "select_goal_next_step":
                            match = re.search(
                                r"Next step:\s*([A-Za-z_][A-Za-z0-9_]*)",
                                str(trace.get("result", "")),
                            )
                            if match:
                                selected_local_name = match.group(1)
                                forced_cloud_name = self._CLOUD_TOOL_NAMES.get(
                                    selected_local_name, selected_local_name
                                )
                            break

                if forced_cloud_name:
                    forced_local_name = next(
                        (
                            name
                            for name, cloud_name in self._CLOUD_TOOL_NAMES.items()
                            if cloud_name == forced_cloud_name
                        ),
                        forced_cloud_name,
                    )
                    forced_handler = self.tool_handlers.get(forced_local_name)
                    forced_declaration = next(
                        (
                            declaration
                            for declaration in self.tool_declarations
                            if isinstance(declaration, dict)
                            and declaration.get("name") == forced_local_name
                        ),
                        None,
                    )
                    required = (
                        forced_declaration.get("parameters", {}).get("required", [])
                        if forced_declaration
                        else []
                    )
                    recovered_args = self._recover_required_tool_arguments(
                        forced_local_name, {}, request_text
                    )
                    required_args_recovered = all(
                        str(recovered_args.get(parameter, "")).strip()
                        for parameter in required
                    )
                    if forced_handler is not None and required_args_recovered:
                        tool_calls = [{
                            "id": f"nova-continuation-{loop_index}",
                            "type": "function",
                            "function": {
                                "name": forced_cloud_name,
                                "arguments": json.dumps(recovered_args),
                            },
                        }]
                        native_tool_calls = False

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
                        parsed_text_call = self._parse_text_tool_call(
                            content,
                            self.tool_declarations,
                        )
                        if parsed_text_call is not None:
                            local_name = parsed_text_call["function"]["name"]
                            parsed_text_call["function"]["name"] = self._CLOUD_TOOL_NAMES.get(
                                local_name, local_name
                            )
                            parsed_text_call["function"]["arguments"] = json.loads(
                                parsed_text_call["function"]["arguments"]
                            )
                            tool_calls = [parsed_text_call]

            content = message.get("content")

            # Some provider models imitate tool calls in text and may use
            # parameter names that do not exist in the registered schema. Retry
            # one recognized malformed text call with that tool's exact schema;
            # never execute guessed or renamed arguments.
            malformed_match = (
                re.search(
                    r"<tool_call>\s*([A-Za-z_][A-Za-z0-9_]*)\b",
                    content,
                    re.IGNORECASE,
                )
                if not tool_calls and isinstance(content, str)
                else None
            )
            if malformed_match:
                malformed_name = malformed_match.group(1)
                malformed_declaration = next(
                    (
                        item for item in self.tool_declarations
                        if isinstance(item, dict)
                        and item.get("name") == malformed_name
                        and malformed_name in self.tool_handlers
                    ),
                    None,
                )
                if malformed_declaration is not None:
                    if malformed_name not in malformed_text_tool_retries:
                        malformed_text_tool_retries.add(malformed_name)
                        cloud_name = self._CLOUD_TOOL_NAMES.get(
                            malformed_name, malformed_name
                        )
                        payload["tools"] = [{
                            "type": "function",
                            "function": {
                                "name": cloud_name,
                                "description": malformed_declaration.get("description", ""),
                                "parameters": self._schema(
                                    malformed_declaration.get("parameters", {})
                                ),
                            },
                        }]
                        payload["tool_choice"] = {
                            "type": "function",
                            "function": {"name": cloud_name},
                        }
                        messages.append({"role": "assistant", "content": content})
                        messages.append({
                            "role": "user",
                            "content": (
                                "Your previous text-form tool call was not executed because "
                                "its arguments did not match the registered schema. Use the "
                                "forced registered function now, with its exact parameter "
                                "names and valid arguments. Do not imitate tool calls in text."
                            ),
                        })
                        continue
                    if not (
                        self.goal_state is not None
                        and self.goal_state.status == "ACTIVE"
                    ):
                        return (
                            "No action executed: the provider repeated a malformed text-form "
                            f"tool call for registered tool '{malformed_name}' after one "
                            "schema-correction retry."
                        )

            # Ordinary chat also needs bounded recovery when a provider invents a
            # tool name. Keep the current registered schema, ask for a valid tool
            # call, and never execute or translate the invented name.
            if malformed_match and malformed_name not in {
                item.get("name") for item in self.tool_declarations
                if isinstance(item, dict)
            } and not (
                self.goal_state is not None
                and self.goal_state.status == "ACTIVE"
            ):
                if malformed_name not in malformed_text_tool_retries:
                    malformed_text_tool_retries.add(malformed_name)
                    payload["tool_choice"] = "auto"
                    messages.append({"role": "assistant", "content": content})
                    messages.append({
                        "role": "user",
                        "content": (
                            f"The tool name '{malformed_name}' is not registered and was not executed. "
                            "Continue the original request using only exact tool names and argument "
                            "schemas present in the available tools. Do not repeat completed actions, "
                            "invent aliases, or imitate tool calls in text."
                        ),
                    })
                    continue
                return (
                    "The unregistered tool call was not executed. The provider repeated "
                    f"the invented tool name '{malformed_name}' after one correction retry."
                )

            # A model may invent a tool name and serialize it as XML. During an
            # active construction goal, never return that imitation as if it
            # were an executed action. Replan through a distinct registered tool.
            if (
                not tool_calls
                and self.goal_state is not None
                and self.goal_state.status == "ACTIVE"
                and isinstance(content, str)
                and "<tool_call>" in content
            ):
                attempted = {
                    str(trace.get("name", ""))
                    for trace in self.last_tool_calls
                    if isinstance(trace, dict)
                    and trace.get("name") not in {"select_goal_next_step", "establish_goal_contract"}
                }
                candidates = [
                    str(item.get("name", "")).strip()
                    for item in self.tool_declarations
                    if isinstance(item, dict)
                    and str(item.get("name", "")).strip() in self.tool_handlers
                    and str(item.get("name", "")).strip() not in attempted
                    and str(item.get("name", "")).strip() not in {
                        "establish_goal_contract", "select_goal_next_step",
                        "self_test", "capability_inventory", "assess_capability_gap",
                    }
                ]
                if candidates:
                    from gemini_agent.goal_next_step import select_goal_next_step
                    selection = select_goal_next_step(
                        self.goal_state.goal,
                        self.goal_state.success_condition,
                        self.goal_state.status,
                        self.goal_state.progress_status,
                        self.goal_state.progress_reason or "The provider returned an unregistered text tool call.",
                        candidates,
                        "\\n".join(self.goal_state.evidence),
                    )
                    selected_name = selection.action
                    if selected_name == "STOP" or selected_name not in candidates:
                        selected_name = "execute_constructed_action" if "execute_constructed_action" in candidates else candidates[0]
                    selected = next(item for item in self.tool_declarations if item.get("name") == selected_name)
                    cloud_name = self._CLOUD_TOOL_NAMES.get(selected_name, selected_name)
                    payload["tools"] = [{
                        "type": "function",
                        "function": {
                            "name": cloud_name,
                            "description": selected.get("description", ""),
                            "parameters": self._schema(selected.get("parameters", {})),
                        },
                    }]
                    payload["tool_choice"] = {"type": "function", "function": {"name": cloud_name}}
                    messages.append({"role": "assistant", "content": content})
                    messages.append({
                        "role": "user",
                        "content": "The previous response named an unregistered tool, so no action was executed. "
                        "Use only the registered tool now forced by the runtime. Supply valid arguments, "
                        "execute one bounded step, and do not imitate tool calls in plain text.",
                    })
                    continue
                return (
                    "Goal remains ACTIVE and unverified. The provider emitted an unregistered text tool call; "
                    "no action was executed, and no distinct registered action remains available in this turn. "
                    "Untrusted model output: " + content[:1000]
                )

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
                        "id": "requested-verify-command-result",                        "type": "function",                        "function": {
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
                    raw_tool_result = ""
                    raw_tool_failed = False
                    goal_replan_pending = False
                    try:
                        args = self._parse_tool_arguments(function.get("arguments", "{}"))
                        args = self._recover_required_tool_arguments(
                            local_name, args, request_text
                        )
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
                        raw_tool_result = str(tool_result)
                        raw_tool_failed = bool(
                            re.search(r"\bExit code:\s*[1-9]\d*\b", raw_tool_result)
                            or re.search(r"\bTool error\s*:", raw_tool_result, re.IGNORECASE)
                            or re.search(r"\bOutcome:\s*(?:FAILED|failure)\b", raw_tool_result, re.IGNORECASE)
                        )
                        tool_result = self._coordinate_tool_failure(
                            local_name=local_name,
                            args=args,
                            tool_result=raw_tool_result,
                            request_text=request_text,
                            learning_request=strategy_goal,
                        )

                    except (json.JSONDecodeError, KeyError, RuntimeError, TypeError, ValueError) as exc:
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
                        bounded_observation_evidence = (
                            self.goal_state.evidence[-1]
                            if self.goal_state.evidence
                            else str(tool_result)[:512]
                        )
                        observation = observe_goal_progress(
                            self.goal_state.goal,
                            self.goal_state.success_condition,
                            bounded_observation_evidence,
                        )
                        self.goal_state.progress_status = observation.status
                        self.goal_state.progress_reason = observation.reason
                        goal_result = str(tool_result)
                        recovery_match = re.search(
                            r"Recovery result:\s*(.*?)(?=\n(?:Diagnosis|Failure learning|Recovery learning):|$)",
                            goal_result,
                            re.IGNORECASE | re.DOTALL,
                        )
                        recovery_result = recovery_match.group(1).strip() if recovery_match else ""
                        if recovery_result:
                            recovery_result = re.split(
                                r"(?:\\\\n|\\n|\\r?\\n)",
                                recovery_result,
                                maxsplit=1,
                            )[0].strip()
                        if not recovery_result:
                            verified_match = re.search(
                                r"(?:Post-action verification|Verification|Postcondition|Outcome)\s*:\s*VERIFIED\b",
                                goal_result,
                                re.IGNORECASE,
                            )
                            if verified_match:
                                recovery_result = goal_result[verified_match.start():]
                                recovery_result = re.split(
                                    r"(?:\\\\n|\\n|\\r?\\n)",
                                    recovery_result,
                                    maxsplit=1,
                                )[0].strip()
                        recovery_verified = bool(
                            raw_tool_failed
                            and recovery_result
                            and re.search(
                                r"(?:Post-action verification|Verification|Postcondition|Outcome)\s*:\s*VERIFIED\b",
                                recovery_result,
                                re.IGNORECASE,
                            )
                        )
                        # Completion evidence must distinguish a recovered failure from an
                        # unresolved failure. A failed step remains FAILED in the ledger, but its
                        # raw Tool error must not poison later completion verification after verified
                        # recovery. Preserve only the bounded verified recovery evidence for recovered
                        # failed steps.
                        normalized_step_evidence = []
                        for step in self.goal_state.steps:
                            step_evidence = str(step.get("evidence", ""))
                            if step.get("status") == "FAILED":
                                verified_step_match = re.search(
                                    r"(?:Post-action verification|Verification|Postcondition|Outcome)\s*:\s*VERIFIED\b",
                                    step_evidence,
                                    re.IGNORECASE,
                                )
                                if verified_step_match:
                                    recovered_evidence = step_evidence[verified_step_match.start():]
                                    recovered_evidence = re.split(
                                        r"(?:\\n|\n|\r?\n)",
                                        recovered_evidence,
                                        maxsplit=1,
                                    )[0].strip()
                                    if recovered_evidence:
                                        normalized_step_evidence.append(recovered_evidence)
                                # Failed attempts remain in the ledger, but an unresolved
                                # historical failure is not proof that the overall goal is
                                # impossible. Replanning may satisfy the same goal by another
                                # path, so keep the failure out of completion evidence unless
                                # it has verified recovery evidence.
                                continue
                            normalized_step_evidence.append(step_evidence)
                        normalized_step_evidence.append(str(tool_result))
                        completion_evidence = "\n".join(
                            [*normalized_step_evidence, f"Observed tool: {local_name}"]
                        )
                        if recovery_verified:
                            normalized_step_evidence = [
                                evidence
                                for evidence in normalized_step_evidence
                                if evidence != str(tool_result)
                            ]
                            # Recovery reports may contain learning/meta text that repeats the
                            # original goal wording. Only the bounded verified recovery evidence should
                            # contribute to goal completion, otherwise metadata can falsely satisfy a
                            # remaining success-condition clause.
                            completion_evidence = "\n".join(
                                [*normalized_step_evidence, recovery_result, f"Observed recovery for: {local_name}"]
                            )
                        if len(completion_evidence) > 3800:
                            completion_evidence = (
                                completion_evidence[:1900]
                                + "\n...\n"
                                + completion_evidence[-1896:]
                            )
                        completion = verify_goal_completion(
                            self.goal_state.goal,
                            self.goal_state.success_condition,
                            completion_evidence,
                        )
                        from gemini_agent.goal_state import step_goal_disposition
                        next_goal_status, goal_replan_pending = step_goal_disposition(
                            completion.status,
                            raw_tool_failed,
                            recovery_verified,
                        )
                        self.goal_state.status = next_goal_status
                        step_status = (
                            "FAILED" if raw_tool_failed
                            else "VERIFIED" if completion.status == "VERIFIED"
                            else "EXECUTED"
                        )
                        self.goal_state.record_step(
                            local_name, step_status, str(tool_result)
                        )
                        if raw_tool_failed or recovery_result:
                            self.goal_state.record_recovery(str(tool_result))
                        self._persist_goal_state()
                        tool_result = (
                            str(tool_result)
                            + "\nGoal progress observation: "
                            + observation.status
                            + "\nGoal progress reason: "
                            + observation.reason
                            + "\nGoal completion verification: "
                            + completion.status
                            + "\nGoal completion reason: "
                            + completion.reason
                            + "\nRuntime goal status: "
                            + self.goal_state.status
                            + "\nGoal steps:"
                            + "".join(
                                f"\n- {step['action']}: {step['status']} | {step['evidence']}"
                                for step in self.goal_state.steps
                            )
                        )
                        goal_verified = self.goal_state.status == "VERIFIED"


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

                    if self.goal_state is not None and self.goal_state.status == "VERIFIED":
                        final_result = str(tool_result)
                        for note in goal_replan_notes:
                            if note not in final_result:
                                final_result += "\n" + note
                        return final_result

                    payload["messages"].append({
                        "role": "tool",
                        "tool_call_id": tool_call.get("id", ""),
                        "content": str(tool_result),
                    })

                    # An unrecoverable-step replan is bounded to one alternative
                    # action. If that action does not verify the goal, stop safely
                    # instead of allowing the provider to wander into more rounds.
                    if (
                        goal_replan_step
                        and local_name == goal_replan_step
                        and self.goal_state is not None
                        and self.goal_state.status != "VERIFIED"
                    ):
                        return (
                            str(tool_result)
                            + "\nGoal replan: Alternative step completed, but the "
                            "goal was not verified. Stopping safely."
                        )

                    # Goal-directed continuation: after each bounded step, reuse
                    # the existing selector against accumulated evidence and allow
                    # one different relevant capability to advance the same goal.
                    if (
                        self.goal_state is not None
                        and self.goal_state.status == "ACTIVE"
                        and not strategy_candidates
                        and re.search(
                            r"\b(?:pursue|continue|work\s+toward|achieve)\b.*\b(?:goal|autonomously|automatically)\b|\bautonomously\b",
                            request_text,
                            re.IGNORECASE | re.DOTALL,
                        )
                    ):
                        from gemini_agent.goal_next_step import select_goal_next_step
                        executed_names = {
                            step["action"]
                            for step in self.goal_state.steps
                            if step.get("status") in {"EXECUTED", "VERIFIED", "FAILED"}
                        }
                        continuation_declarations = self.tool_declarations
                        continuation_candidates = [
                            str(declaration.get("name", "")).strip()
                            for declaration in continuation_declarations
                            if (
                                isinstance(declaration, dict)
                                and str(declaration.get("name", "")).strip()
                                and str(declaration.get("name", "")).strip() not in executed_names
                                and str(declaration.get("name", "")).strip() not in {
                                    "establish_goal_contract", "select_goal_next_step",
                                    "self_test", "capability_inventory", "assess_capability_gap",
                                }
                            )
                        ]
                        if continuation_candidates:
                            continuation_evidence = "\n".join(self.goal_state.evidence)
                            if len(continuation_evidence) > 480:
                                continuation_evidence = (
                                    continuation_evidence[:238]
                                    + "\n...\n"
                                    + continuation_evidence[-237:]
                                )
                            continuation_selection = select_goal_next_step(
                                self.goal_state.goal,
                                self.goal_state.success_condition,
                                self.goal_state.status,
                                self.goal_state.progress_status,
                                self.goal_state.progress_reason,
                                continuation_candidates,
                                continuation_evidence,
                            )
                            if continuation_selection.action in self.tool_handlers:
                                next_action = continuation_selection.action
                                if goal_replan_pending:
                                    replan_note = (
                                        "Goal replan: "
                                        f"Selected alternative step {next_action} after the failed step."
                                    )
                                    goal_replan_notes.append(replan_note)
                                    goal_replan_step = next_action
                                    tool_result = str(tool_result).replace(
                                        "Runtime goal status: FAILED",
                                        "Runtime goal status: ACTIVE",
                                    )
                                    tool_result += "\n" + replan_note
                                self.last_tool_calls.append({
                                    "name": "select_goal_next_step",
                                    "args": {
                                        "goal": self.goal_state.goal,
                                        "success_condition": self.goal_state.success_condition,
                                        "goal_status": self.goal_state.status,
                                        "progress_status": self.goal_state.progress_status,
                                        "progress_reason": self.goal_state.progress_reason,
                                        "candidates": continuation_candidates,
                                        "evidence": "\n".join(self.goal_state.evidence),
                                    },
                                    "result": (
                                        f"Next step: {next_action}\n"
                                        f"Reason: {continuation_selection.reason}"
                                    ),
                                })
                                next_cloud_name = self._CLOUD_TOOL_NAMES.get(next_action, next_action)
                                next_declaration = next(
                                    (
                                        declaration
                                        for declaration in self.tool_declarations
                                        if declaration.get("name") == next_action
                                    ),
                                    None,
                                )
                                if next_declaration is not None:
                                    payload["tools"] = [{
                                        "type": "function",
                                        "function": {
                                            "name": next_cloud_name,
                                            "description": next_declaration["description"],
                                            "parameters": self._schema(next_declaration["parameters"]),
                                        },
                                    }]
                                    payload["tool_choice"] = {
                                        "type": "function",
                                        "function": {"name": next_cloud_name},
                                    }
                            elif goal_replan_pending:
                                self.goal_state.status = "FAILED"
                                self._persist_goal_state()
                                tool_result += (
                                    "\nGoal replan: No viable alternative step was found; "
                                    "goal cannot continue safely."
                                )

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

                # Adaptive investigation must distinguish persistence from progress.
                # A second consecutive round with the exact same tool inputs and
                # observed results contains no new evidence. Give the model one
                # explicit chance to reassess with tools disabled rather than
                # spending the remaining safety budget repeating the same path.
                round_observations = self.last_tool_calls[round_trace_start:]
                if round_observations:
                    observation_signature = json.dumps(
                        [
                            {
                                "name": item.get("name"),
                                "args": item.get("args"),
                                "result": item.get("result"),
                            }
                            for item in round_observations
                        ],
                        sort_keys=True,
                        default=str,
                    )
                    if observation_signature == last_observation_signature:
                        payload["messages"].append({
                            "role": "user",
                            "content": (
                                "The latest investigation round repeated exactly the same "
                                "observation and produced no new evidence. Do not repeat that "
                                "mechanism or identical call. Reassess the current evidence, "
                                "use a genuinely distinct safe mechanism only if it can add "
                                "new information, otherwise synthesize the best-supported "
                                "answer and state the remaining uncertainty explicitly."
                            ),
                        })
                        if not self._exclude_repeated_observation_tools(
                            payload, round_observations
                        ):
                            return (
                                "Investigation stopped safely: the latest round repeated "
                                "the same observation, and no distinct registered tool "
                                "remains to gather new evidence. No result was claimed "
                                "without verification."
                            )
                        last_observation_signature = None
                        continue
                    last_observation_signature = observation_signature

                # Deterministic explicit read-only/local requests do not need a
                # second Cloudflare round-trip. Return the local tool result directly.
                if self._should_return_tool_result_directly(requested_tool, loop_index):
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
            if self.goal_state is not None and is_premature_blocker_claim(
                self.goal_state.status, str(content)
            ):
                if goal_blocker_rejections >= 2:
                    return (
                        "Goal remains ACTIVE and unverified. Nova rejected the terminal "
                        "blocker claim because the available evidence does not establish "
                        "that recovery paths were exhausted. Latest claim: "
                        + str(content)[:1200]
                    )

                goal_blocker_rejections += 1
                payload["messages"].append({
                    "role": "assistant",
                    "content": str(content),
                })
                payload["messages"].append({
                    "role": "user",
                    "content": (
                        "Runtime rejection: your terminal blocker claim is not accepted as "
                        "evidence that the active goal is impossible. Continue the goal. "
                        "Choose and execute a distinct, registered investigation/action; do "
                        "not repeat an already executed action. A tool missing from one "
                        "discovery result does not prove it is absent from the environment. "
                        "Inspect alternative mechanisms and available installation or "
                        "substitution paths where safe. Only report a blocker after observed "
                        "results establish why the viable alternatives cannot meet the "
                        "success condition. Never claim success without independent evidence."
                    ),
                })

                executed_names = {
                    str(step.get("action", ""))
                    for step in self.goal_state.steps
                    if step.get("status") in {"EXECUTED", "VERIFIED", "FAILED"}
                }
                candidate_declarations = [
                    declaration
                    for declaration in self.tool_declarations
                    if isinstance(declaration, dict)
                    and isinstance(declaration.get("name"), str)
                    and declaration["name"] in self.tool_handlers
                    and declaration["name"] not in executed_names
                    and declaration["name"] not in {
                        "establish_goal_contract", "select_goal_next_step",
                        "self_test", "capability_inventory", "assess_capability_gap",
                    }
                ][:256]
                if candidate_declarations:
                    candidate_names = [
                        declaration["name"] for declaration in candidate_declarations
                    ]
                    evidence = "\n".join(self.goal_state.evidence)
                    if len(evidence) > 480:
                        evidence = evidence[:238] + "\n...\n" + evidence[-237:]
                    from gemini_agent.goal_next_step import select_goal_next_step
                    selection = select_goal_next_step(
                        self.goal_state.goal,
                        self.goal_state.success_condition,
                        "ACTIVE",
                        "BLOCKED",
                        "The model asserted a blocker without sufficient observed evidence.",
                        candidate_names,
                        evidence or "No independent evidence establishes that all recovery paths failed.",
                    )
                    selected_name = selection.action
                    if selected_name not in candidate_names:
                        selected_name = (
                            "execute_constructed_action"
                            if "execute_constructed_action" in candidate_names
                            else candidate_names[0]
                        )
                    declaration = next(
                        item for item in candidate_declarations
                        if item["name"] == selected_name
                    )
                    cloud_name = self._CLOUD_TOOL_NAMES.get(selected_name, selected_name)
                    payload["tools"] = [{
                        "type": "function",
                        "function": {
                            "name": cloud_name,
                            "description": declaration["description"],
                            "parameters": self._schema(declaration["parameters"]),
                        },
                    }]
                    payload["tool_choice"] = {
                        "type": "function",
                        "function": {"name": cloud_name},
                    }
                    continue

                return (
                    "Goal remains ACTIVE and unverified. A blocker claim was rejected, "
                    "but no unexecuted registered action remains available for a distinct "
                    "investigation. Evidence: " + str(content)[:1200]
                )
            return str(content)

        raise RuntimeError(
            self._tool_loop_exhaustion_diagnostic(
                max_tool_rounds, self.last_tool_calls, self.goal_state
            )
        )

    @staticmethod
    def _audit_explicit_calculation_sequence(
        prompt: str, answer: str, tool_calls: list[dict]
    ) -> str:
        """Reject completion claims when an explicit calculation sequence lacks tool evidence."""
        match = re.search(
            r"calculate\s+([0-9\s()+\-*/%.]+?)\s*,?\s*then\s+independently\s+verify\s+the\s+result\s+by\s+calculating\s+([0-9\s()+\-*/%.]+?)(?:[.!?]|$)",
            str(prompt),
            re.IGNORECASE,
        )
        if not match:
            return answer
        required = [
            re.sub(r"\s+", "", match.group(index)).rstrip(".")
            for index in (1, 2)
        ]
        recorded = {
            re.sub(r"\s+", "", str(call.get("args", {}).get("expression", ""))).rstrip(".")
            for call in tool_calls
            if isinstance(call, dict)
            and call.get("name") == "calculator"
            and isinstance(call.get("args"), dict)
        }
        missing = [expression for expression in required if expression not in recorded]
        if not missing:
            return answer
        observed = [
            {"expression": call.get("args", {}).get("expression"), "result": call.get("result")}
            for call in tool_calls
            if isinstance(call, dict)
            and call.get("name") == "calculator"
            and isinstance(call.get("args"), dict)
        ]
        return (
            "Execution incomplete: required calculator calls are missing; completion cannot be claimed. "
            f"Missing expressions: {', '.join(missing)}. Recorded calculator evidence: "
            + json.dumps(observed, ensure_ascii=False, default=str)
        )

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
        prompt_text = str(prompt)
        resume_requested = prompt_text.strip().lower() in {"/resume", "resume active goal", "resume the active goal"}
        if resume_requested:
            try:
                self.goal_state = load_goal_state()
            except (OSError, ValueError) as exc:
                return f"Cannot resume the persisted goal safely: {exc}. The saved record was left unchanged."
            if self.goal_state is None:
                return "No persisted active goal is available to resume."
            prior_steps = "\n".join(
                f"- {step['action']}: {step['status']} | {step['evidence']}"
                for step in self.goal_state.steps
            ) or "None recorded."
            prior_recoveries = "\n".join(self.goal_state.recovery_history) or "None recorded."
            prior_evidence = "\n".join(self.goal_state.evidence) or "None recorded."
            prompt_text = (
                "Resume the persisted active goal below. Keep its original success criteria unchanged. "
                "Inspect current reality and existing artifacts before repeating any previously attempted action. "
                "Use prior evidence to diagnose failures, choose a distinct viable next step where appropriate, "
                "and continue until independently verified complete or a concrete, evidenced blocker remains.\n"
                f"Goal: {self.goal_state.goal}\n"
                f"Success condition: {self.goal_state.success_condition}\n"
                f"Prior evidence: {prior_evidence}\n"
                f"Prior steps:\n{prior_steps}\n"
                f"Recovery history:\n{prior_recoveries}\n"
                "Do not claim success from prior narration; verify the actual outcome."
            )
            contents[-1]["parts"][0]["text"] = prompt_text
        else:
            self.goal_state = None
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
        # Explicit autonomy-boundary assessments are deterministic, read-only policy
        # decisions. Dispatch them before any provider round-trip so the model cannot
        # reinterpret the supplied uncertainty or risk constraints.
        if requested_tool == "assess_autonomy_boundary":
            patterns = {
                "goal": r'\b(?:the )?goal\s+"([^"]+)"',
                "outcome_state": r'\boutcome state\s*[:=]?\s*(ACHIEVED|VERIFIED|COMPLETE|COMPLETED|MISMATCH|FAILED|CONTRADICTED|PARTIAL_OR_UNCERTAIN|INCONCLUSIVE|MISMATCH_OR_UNKNOWN|UNKNOWN|UNKNOWN_MISMATCH)',
                "uncertainty": r'\buncertainty\s*(?:is|was|:)?\s*"([^"]+)"',
                "observed_evidence": r'\b(?:observed evidence|supplied observed evidence)\s*(?:is|was|:)?\s*"([^"]+)"',
                "available_actions": r'\bavailable actions\s*(?:are|is|were|:)?\s*"([^"]+)"',
                "risk_constraints": r'\brisk constraints\s*(?:are|is|were|:)?\s*"([^"]+)"',
            }
            extracted = {}
            for key, pattern in patterns.items():
                match = re.search(pattern, prompt_text, re.IGNORECASE | re.DOTALL)
                if match:
                    extracted[key] = match.group(1).strip() if key != "outcome_state" else match.group(1).upper()
            if all(key in extracted for key in patterns):
                result = str(self.tool_handlers[requested_tool](**extracted))
                self.last_tool_calls.append({"name": requested_tool, "args": extracted, "result": result})
                return result
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
        # Explicit construction requests enter the existing bounded goal loop.
        # This is only activated when the user explicitly requires construction,
        # execution, and verification, so ordinary descriptive requests remain
        # conversational and do not gain autonomous mutation semantics.
        explicit_autonomy_commitment = (
            re.search(
                r"\bdo not ask me to (?:write|modify|install|create|build)\b",
                prompt_text,
                re.IGNORECASE,
            )
            or re.search(
                r"\b(?:maintain|keep|retain)\s+ownership\b|\bcontinue\s+until\b",
                prompt_text,
                re.IGNORECASE,
            )
            or re.search(
                r"\bcontinue\b.{0,100}\buntil\b.{0,100}\b(?:verified|verify|complete|completed|blocker)\b",
                prompt_text,
                re.IGNORECASE | re.DOTALL,
            )
        )
        constructive_autonomy = (
            re.search(
                r"\b(?:construct|build|building|create|generate|make|implement|install)\b",
                prompt_text,
                re.IGNORECASE,
            )
            and re.search(
                r"\b(?:execute|run|build|building|install|produce|deliver|test|testing)\b",
                prompt_text,
                re.IGNORECASE,
            )
            and re.search(r"\bverif\w*\b", prompt_text, re.IGNORECASE)
            and explicit_autonomy_commitment
        )
        if not resume_requested and constructive_autonomy:
            sentences = [
                part.strip()
                for part in re.split(r"(?<=[.!?])\s+", prompt_text)
                if part.strip()
            ]
            goal = sentences[0] if sentences else prompt_text.strip()
            if goal.lower().startswith("continue from "):
                # Preserve the task context when the prompt resumes a workflow.
                goal = prompt_text.strip()
            success_candidates = [
                sentence
                for sentence in sentences
                if not re.match(
                    r"\s*(?:report|summarize|list|describe)\b",
                    sentence,
                    re.IGNORECASE,
                )
                and re.search(
                    r"\b(?:build|building|create|produce|deliver|verify|install|testing|test)\b",
                    sentence,
                    re.IGNORECASE,
                )
                and re.search(
                    r"\b(?:verify|evidence|result|outcome|artifact|success|apk|addition|subtraction|multiplication|division|test|testing|installation)\b",
                    sentence,
                    re.IGNORECASE,
                )
            ]
            # Prefer the sentence that specifies the most concrete acceptance
            # criteria. A later reporting sentence may mention "test results" but
            # must not replace the actual build/test requirements.
            success = max(
                success_candidates,
                key=lambda sentence: sum(
                    len(re.findall(pattern, sentence, re.IGNORECASE))
                    for pattern in (
                        r"\bapk\b",
                        r"\baddition\b",
                        r"\bsubtraction\b",
                        r"\bmultiplication\b",
                        r"\bdivision\b",
                        r"\b(?:test|testing)\b",
                        r"\binstallation\b",
                        r"\b(?:artifact|outcome|evidence|success)\b",
                        r"\b(?:build|building|create|produce|deliver|verify|install)\b",
                    )
                ),
                default="",
            )
            if goal and success:
                goal = goal[:512]
                success = success[:512]
                # The runtime, not the language model, owns goal initialization.
                # Asking the model to establish its own contract lets it narrate
                # the contract instead of entering the bounded execution loop.
                self.goal_state = start_goal_state(goal, success)
                self._persist_goal_state()
                contents[-1]["parts"][0]["text"] = (
                    str(contents[-1]["parts"][0]["text"])
                    + "\n\n[Nova orchestration directive] "
                    + f"Nova has already established the runtime goal contract. Goal: \"{goal}\". "
                    + f"Success condition: \"{success}\". Runtime status: ACTIVE. "
                    + "Autonomously pursue the goal using bounded next-step selection, "
                    + "registered constructed-action execution, recovery, and independent "
                    + "outcome verification. Only actual registered tool executions and their "
                    + "returned results count as execution evidence. Never narrate or invent "
                    + "tool calls, command output, file creation, build results, or verification. "
                    + "If no registered action can make progress, report the concrete blocker "
                    + "without claiming completion."
                )
        answer = self._generate_cloudflare(contents, system_instruction)
        return self._audit_explicit_calculation_sequence(
            prompt_text, answer, self.last_tool_calls
        )