"""Small, safe local tools available to Nova."""

import ast
import datetime as dt
import fnmatch
import hashlib
import inspect
import json
import re
import operator
import shlex
import shutil
import subprocess
import shutil
import os
import platform
import socket
import tempfile
import time
from collections.abc import Callable
from pathlib import Path


_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_MAX_READ_BYTES = 64 * 1024
_MAX_FIND_RESULTS = 100
_MAX_SEARCH_RESULTS = 100
_MAX_WRITE_BYTES = 64 * 1024


def _evaluate(node: ast.AST) -> float | int:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_evaluate(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_evaluate(node.left), _evaluate(node.right))
    raise ValueError("Only basic arithmetic is supported.")


def calculator(expression: str) -> str:
    """Evaluate basic arithmetic without executing arbitrary Python."""
    try:
        tree = ast.parse(expression, mode="eval")
        return str(_evaluate(tree.body))
    except (SyntaxError, ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError(f"Invalid arithmetic expression: {exc}") from exc

def capability_inventory() -> str:
    """List the capabilities Nova currently exposes to its local tool runtime."""
    entries = []
    for declaration in TOOL_DECLARATIONS:
        name = declaration.get("name")
        description = declaration.get("description", "")
        if name in TOOL_HANDLERS:
            entries.append(f"- {name}: {description}")
    return f"Capabilities ({len(entries)}):\n" + "\n".join(entries)




def send_android_keyevent(keycode: str) -> str:
    """Send one bounded Android key event through the manually entered root shell."""
    if not isinstance(keycode, str) or not keycode.strip():
        raise ValueError("Keycode cannot be empty.")
    allowed = {"3", "4", "25", "27"}
    normalized = keycode.strip().upper().replace("KEYCODE_", "")
    aliases = {"HOME": "3", "BACK": "4", "VOLUME_DOWN": "25", "CAMERA": "27"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in allowed:
        raise ValueError("Unsupported Android keycode. Allowed actions: HOME, BACK, VOLUME_DOWN, CAMERA.")
    result = _run_bounded_root_action(f"input keyevent {normalized}")
    return f"Android key event {normalized} sent.\n{result}"

def send_android_intent(action: str) -> str:
    """Launch one explicitly allowlisted Android intent action."""
    if not isinstance(action, str) or not action.strip():
        raise ValueError("Intent action cannot be empty.")
    normalized = action.strip()
    aliases = {"IMAGE_CAPTURE": "android.media.action.IMAGE_CAPTURE"}
    normalized = aliases.get(normalized, normalized)
    allowed_actions = {"android.media.action.IMAGE_CAPTURE"}
    if normalized not in allowed_actions:
        raise ValueError("Unsupported Android intent action.")
    result = _run_bounded_root_action(f"am start -a {normalized}")
    return f"Android intent {normalized} started.\n{result}"


def discover_camera_control() -> str:
    """Inspect Android for safe camera control mechanisms and foreground the camera for UI inspection."""
    results = []

    for executable in ("cmd", "dumpsys", "am"):
        results.append(f"{executable}: {find_executable(executable)}")

    diagnostics = (
        (
            "image-capture activity",
            "cmd package resolve-activity --brief -a android.media.action.IMAGE_CAPTURE",
        ),
        (
            "still-image camera activity",
            "cmd package resolve-activity --brief -a android.media.action.STILL_IMAGE_CAMERA",
        ),
        ("camera service", "dumpsys media.camera"),
    )
    for label, command in diagnostics:
        try:
            result = run_root_command(command)
        except (RuntimeError, ValueError) as exc:
            result = f"Diagnostic unavailable: {exc}"
        results.append(f"{label}:\n{result}")

    # The UI hierarchy is only meaningful when the camera is foregrounded.
    # Launch the still-image camera through the bounded action primitive first,
    # then perform the read-only hierarchy dump.
    try:
        launch_result = _run_bounded_root_action(
            "am start -a android.media.action.STILL_IMAGE_CAMERA"
        )
    except (RuntimeError, ValueError) as exc:
        launch_result = f"Camera foregrounding unavailable: {exc}"
    results.append(f"camera foreground launch:\n{launch_result}")

    try:
        hierarchy = _dump_camera_ui_hierarchy()
    except (RuntimeError, ValueError) as exc:
        hierarchy = f"Diagnostic unavailable: {exc}"
    results.append(f"camera UI hierarchy:\n{hierarchy}")

    return (
        "Camera control environment discovery:\n"
        + "\n".join(results)
        + "\nCamera was foregrounded for UI inspection; no shutter action was performed."
    )

def assess_capability_gap(request: str) -> str:
    """Determine whether Nova has a plausible local capability for a request."""
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Request cannot be empty.")

    text = request.lower()
    capability_phrases = {
        "camera control": {"camera control": ["discover_camera_control"]},
        "camera shutter mechanism": {"camera shutter mechanism": ["discover_camera_control"]},
        "battery": {"battery": ["get_system_battery_status"]},
        "date and time": {"date and time": ["current_datetime"]},
        "current time": {"current time": ["current_datetime"]},
        "wifi": {"wifi": ["get_wifi_status"]},
        "wi-fi": {"wi-fi": ["get_wifi_status"]},
        "bluetooth": {"bluetooth": ["get_bluetooth_status"]},
        "airplane mode": {"airplane mode": ["get_airplane_mode"]},
        "screen brightness": {"screen brightness": ["get_screen_brightness"]},
        "screen orientation": {"screen orientation": ["get_screen_orientation"]},
        "screen resolution": {"screen resolution": ["get_screen_resolution"]},
        "screen refresh rate": {"screen refresh rate": ["get_screen_refresh_rate"]},
        "screen timeout": {"screen timeout": ["get_screen_timeout"]},
        "memory usage": {"memory usage": ["get_system_memory_usage"]},
        "cpu usage": {"cpu usage": ["get_system_cpu_usage"]},
        "system information": {"system information": ["get_system_info"]},
        "system info": {"system info": ["get_system_info"]},
        "hostname": {"hostname": ["get_hostname"]},
        "network interfaces": {"network interfaces": ["get_network_interfaces"]},
        "calculator": {"calculator": ["calculator"]},
        "calculate": {"calculate": ["calculator"]},
        "arithmetic": {"arithmetic": ["calculator"]},
        "capabilities": {"capabilities": ["capability_inventory"]},
        "self-test": {"self-test": ["self_test"]},
        "self test": {"self test": ["self_test"]},
    }

    matches = []
    for phrase, mapping in capability_phrases.items():
        if phrase in text:
            for names in mapping.values():
                matches.extend(names)

    if matches:
        unique = list(dict.fromkeys(matches))
        return f"Capability match: {', '.join(unique)}."

    return (
        "Capability gap: no plausible local capability matches this request. "
        "Nova must not invent a tool or pretend the capability exists."
    )


def plan_capability_extension(request: str) -> str:
    """Create a bounded implementation plan for a capability Nova does not currently expose."""
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Request cannot be empty.")

    gap = assess_capability_gap(request)
    if gap.startswith("Capability match:"):
        return f"Extension not needed: {gap}"

    normalized = re.sub(r"[^a-z0-9]+", " ", request.lower()).strip()

    # Prefer stable semantic names for common requests instead of deriving a
    # tool name from model-generated filler such as "add a capability to".
    canonical_capabilities = (
        (("camera shutter", "capture a photo", "take a photo", "open the device camera", "open device camera"),
         "camera_shutter"),
    )
    for phrases, suffix in canonical_capabilities:
        if any(phrase in normalized for phrase in phrases):
            tool_name = f"extend_{suffix}"
            break
    else:
        words = [word for word in normalized.split() if word not in {
            "the", "a", "an", "to", "of", "do", "i", "have", "can", "you",
            "capability", "capabilities", "control", "phone", "add",
            "device", "open", "this",
        }]
        suffix = "_".join(words[:5]) or "requested_capability"
        tool_name = f"extend_{suffix}"

    return (
        "Extension plan: capability is missing.\n"
        f"Requested capability: {request.strip()}\n"
        f"Proposed tool: {tool_name}\n"
        "Implementation boundary: inspect Android reality first; do not assume an API, "
        "permission, executable, or service exists.\n"
        "Implementation steps: discover the narrowest supported mechanism; implement a "
        "bounded tool with explicit inputs and safety checks; register its declaration and "
        "handler; add deterministic unit tests; run the real-device test; only then expose "
        "the capability to Nova.\n"
        "Verification: execute the new capability on the device and verify the resulting "
        "state or observable output.\n"
        "Status: plan only; no code or device state was modified."
    )


def _run_extension_test_suite() -> tuple[bool, str]:
    """Run Nova's deterministic test suite as part of an extension transaction."""
    try:
        completed = subprocess.run(
            [os.sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_gemini_*.py", "-q"],
            cwd=_filesystem_root(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "Extension verification failed: deterministic test suite timed out after 30 seconds."
    except OSError as exc:
        return False, f"Extension verification failed: could not start deterministic test suite: {exc}"

    output = (completed.stdout or "").strip()
    if completed.returncode != 0:
        if len(output) > 4096:
            output = output[-4096:]
        return False, f"Extension verification failed: deterministic test suite failed.\n{output}"
    return True, "Extension verification: deterministic test suite passed."


def _extension_registered_capability_error(original: str, updated: str, request: str) -> str | None:
    """Reject source edits that declare a new tool without implementing it."""
    plan = plan_capability_extension(request)
    prefix = "Proposed tool: "
    if prefix not in plan:
        return "Extension not applied: could not determine the proposed capability name."
    proposed = plan.split(prefix, 1)[1].splitlines()[0].strip()
    if proposed.startswith("extend_"):
        proposed = proposed[len("extend_"):]
    if not proposed:
        return "Extension not applied: proposed capability name is empty."

    def source_names(source: str) -> set[str]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return set()
        names = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(node.name)
        return names

    def literal_tool_names(source: str) -> set[str]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return set()
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant) and key.value == "name":
                        if isinstance(value, ast.Constant) and isinstance(value.value, str):
                            names.add(value.value)
        return names

    def handler_keys(source: str) -> set[str]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return set()
        keys = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                targets = node.targets
                value = node.value
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
                value = node.value
            else:
                continue
            if not any(
                isinstance(target, ast.Name) and target.id == "TOOL_HANDLERS"
                for target in targets
            ):
                continue
            if isinstance(value, ast.Dict):
                for key in value.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        keys.add(key.value)
        return keys

    before_names = literal_tool_names(original)
    after_names = literal_tool_names(updated)
    added_names = after_names - before_names
    if proposed not in added_names:
        return (
            f"Extension not applied: proposed capability '{proposed}' was not added "
            "as a new tool declaration."
        )

    functions = source_names(updated)
    handlers = handler_keys(updated)
    missing = []
    if proposed not in functions:
        missing.append("implementation function")
    if proposed not in handlers:
        missing.append("TOOL_HANDLERS registration")
    if missing:
        return (
            f"Extension not applied: capability '{proposed}' is declared but missing "
            + " and ".join(missing)
            + ". A declaration alone is not an implementation."
        )
    return None


def _normalize_extension_fragment(fragment: str) -> str:
    """Normalize model-copied source excerpts without changing source semantics."""
    value = fragment.replace("\r\n", "\n").replace("\r", "\n")
    lines = value.split("\n")
    normalized = []
    for line in lines:
        match = re.match(r"^\s*\d+: ?(.*)$", line)
        normalized.append(match.group(1) if match else line)
    return "\n".join(normalized)

def apply_capability_extension(
    request: str,
    path: str,
    implementation_kind: str,
    implementation_target: str,
    implementation_args: str,
    declaration_description: str,
) -> str:
    """Apply a bounded extension built only from an existing local primitive."""
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Request cannot be empty.")
    if not isinstance(path, str) or not path.strip():
        raise ValueError("Path cannot be empty.")
    if not isinstance(implementation_kind, str) or not implementation_kind.strip():
        raise ValueError("Implementation kind cannot be empty.")
    if not isinstance(implementation_target, str) or not implementation_target.strip():
        raise ValueError("Implementation target cannot be empty.")
    if not isinstance(implementation_args, str):
        raise ValueError("Implementation args must be text.")
    if not isinstance(declaration_description, str) or not declaration_description.strip():
        raise ValueError("Declaration description cannot be empty.")
    if any(ord(char) < 32 and char not in "\t" for char in declaration_description):
        return "Extension not applied: declaration description contains unsupported control characters."

    gap = assess_capability_gap(request)
    if not gap.startswith("Capability gap:"):
        return f"Extension not applied: {gap}"

    plan = plan_capability_extension(request)
    if plan.startswith("Extension not needed:"):
        return f"Extension not applied: {plan}"

    target = _safe_path(path)
    relative = target.relative_to(_filesystem_root()).as_posix()
    if relative != "gemini_agent/tools.py":
        raise ValueError("Structured capability extensions must target gemini_agent/tools.py.")
    if not target.exists() or not target.is_file() or target.is_symlink():
        return f"Extension not applied: target is not a regular source file: {relative}"

    plan = plan_capability_extension(request)
    if plan.startswith("Extension blocked:"):
        return plan
    proposed = plan.split("Proposed tool: ", 1)[1].splitlines()[0].strip()
    if proposed.startswith("extend_"):
        proposed = proposed[len("extend_"):]

    kind = implementation_kind.strip().lower()
    target_name = implementation_target.strip()
    if kind != "existing_tool":
        return (
            "Extension not applied: implementation_kind must be 'existing_tool'. "
            "Nova may only compose capabilities from primitives that already exist locally."
        )
    available_targets = set(TOOL_HANDLERS)
    if target_name not in available_targets:
        available = ", ".join(sorted(available_targets))
        return (
            f"Extension not applied: existing local tool '{target_name}' is not available. "
            f"Valid implementation targets are: {available}"
        )
    if target_name == proposed:
        return "Extension not applied: extension primitive must be an existing capability, not the new capability itself."

    # Discovery, planning, validation, and health-check tools are observations,
    # not implementation primitives. Keep this generic so new capabilities do
    # not require a hard-coded exception in the extension engine.
    extension_only_tools = {
        "assess_capability_gap",
        "plan_capability_extension",
        "apply_capability_extension",
        "capability_inventory",
        "self_test",
        "discover_camera_control",
        "find_executable",
        "diagnose_command_failure",
        "verify_command_result",
    }
    if target_name in extension_only_tools:
        return (
            f"Extension blocked: '{target_name}' is an inspection or orchestration tool, "
            "not an implementation primitive. Nova must choose an action-capable local "
            "primitive discovered in the environment."
        )

    try:
        primitive_signature = inspect.signature(TOOL_HANDLERS[target_name])
    except (TypeError, ValueError) as exc:
        return f"Extension not applied: could not inspect primitive '{target_name}': {exc}"

    function_node = ast.FunctionDef(
        name=proposed,
        args=ast.arguments(
            posonlyargs=[],
            args=[],
            kwonlyargs=[],
            kw_defaults=[],
            defaults=[],
        ),
        body=[
            ast.Return(
                value=ast.Call(
                    func=ast.Name(id="_run_extension_primitive", ctx=ast.Load()),
                    args=[ast.Constant(value=target_name), ast.Constant(value=implementation_args.strip())],
                    keywords=[],
                )
            )
        ],
        decorator_list=[],
        returns=ast.Name(id="str", ctx=ast.Load()),
    )
    function_source = ast.unparse(ast.fix_missing_locations(function_node))

    declaration = (
        "    {\n"
        f'        "name": "{proposed}",\n'
        f'        "description": {declaration_description.strip()!r},\n'
        '        "parameters": {"type": "OBJECT", "properties": {}},\n'
        "    },\n"
    )
    handler_line = f'    "{proposed}": {proposed},\n'

    declaration_index = original.find(declaration_marker)
    handler_index = original.find(handler_marker)
    if declaration_index < 0 or handler_index < 0:
        return "Extension not applied: required top-level tool integration anchors were not found."

    declaration_end = original.find("\n]\n", declaration_index)
    if declaration_end < 0:
        return "Extension not applied: TOOL_DECLARATIONS closing anchor was not found."
    updated = (
        original[:declaration_end]
        + "\n"
        + declaration.rstrip("\n")
        + original[declaration_end:]
    )

    handler_index = updated.rfind(handler_marker)
    handler_end = updated.find("\n}\n", handler_index)
    if handler_index < 0 or handler_end < 0:
        return "Extension not applied: TOOL_HANDLERS closing anchor was not found."
    updated = (
        updated[:handler_end]
        + "\n"
        + handler_line.rstrip("\n")
        + updated[handler_end:]
    )

    helper_marker = "\ndef self_test()"
    helper_source = (
        "\ndef _run_extension_primitive(tool_name: str, arguments: str) -> str:\n"
        "    handler = TOOL_HANDLERS.get(tool_name)\n"
        "    if handler is None:\n"
        "        raise ValueError(f\"Unknown extension primitive: {tool_name}\")\n"
        "    parsed = json.loads(arguments) if arguments.strip() else {}\n"
        "    if not isinstance(parsed, dict):\n"
        "        raise ValueError(\"Extension primitive arguments must be a JSON object.\")\n"
        "    return str(handler(**parsed))\n"
    )
    if helper_marker not in updated:
        return "Extension not applied: implementation insertion anchor was not found."
    updated = updated.replace(
        helper_marker,
        "\n" + function_source + helper_source + helper_marker,
        1,
    )

    try:
        ast.parse(updated, filename=relative)
    except SyntaxError as exc:
        generated_lines = updated.splitlines()
        line = generated_lines[exc.lineno - 1] if exc.lineno and 0 < exc.lineno <= len(generated_lines) else "<unavailable>"
        return (
            "Extension not applied: internally generated source is invalid Python: "
            f"{exc}. Offending line: {line!r}"
        )

    registration_error = _extension_registered_capability_error(original, updated, request)
    if registration_error:
        return registration_error

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.extension-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(updated)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, target)
    except OSError as exc:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        return f"Extension not applied: source write failed: {exc}"