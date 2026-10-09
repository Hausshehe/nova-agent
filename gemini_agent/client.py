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
    def _tool_loop_failure_context(
        max_tool_rounds: int, tool_calls: list[dict], goal_state
    ) -> dict:
        """Summarize bounded execution evidence when the provider loop is exhausted."""
        context = self._tool_loop_failure_context(
            max_tool_rounds, self.last_tool_calls, self.goal_state
        )
        raise RuntimeError(
            "Cloudflare requested too many tool calls; "
            + json.dumps(context, sort_keys=True, default=str)
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
        constructive_autonomy = (
            re.search(r"\b(?:construct|build|create|generate|make|implement)\b", prompt_text, re.IGNORECASE)
            and re.search(r"\b(?:execute|run)\b", prompt_text, re.IGNORECASE)
            and re.search(r"\bverify\w*\b", prompt_text, re.IGNORECASE)
            and re.search(r"\bdo not ask me to (?:write|modify)\b", prompt_text, re.IGNORECASE)
        )
        if constructive_autonomy:
            sentences = [
                part.strip()
                for part in re.split(r"(?<=[.!?])\s+", prompt_text)
                if part.strip()
            ]
            goal = sentences[0] if sentences else prompt_text.strip()
            success = next(
                (
                    sentence
                    for sentence in reversed(sentences)
                    if re.search(r"\b(?:build|create|produce|deliver|verify)\b", sentence, re.IGNORECASE)
                    and re.search(r"\b(?:verify|evidence|result|outcome|artifact|success)\b", sentence, re.IGNORECASE)
                ),
                "",
            )
            if goal and success:
                goal = goal[:512]
                success = success[:512]
                # The runtime, not the language model, owns goal initialization.
                # Asking the model to establish its own contract lets it narrate
                # the contract instead of entering the bounded execution loop.
                self.goal_state = start_goal_state(goal, success)
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
        return self._generate_cloudflare(contents, system_instruction)