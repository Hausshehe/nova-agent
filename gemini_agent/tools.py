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

def resolve_android_intent(action: str) -> str:
    """Resolve one allowlisted Android intent without launching it."""
    if not isinstance(action, str) or not action.strip():
        raise ValueError("Intent action cannot be empty.")
    normalized = action.strip()
    aliases = {
        "IMAGE_CAPTURE": "android.media.action.IMAGE_CAPTURE",
        "STILL_IMAGE_CAMERA": "android.media.action.STILL_IMAGE_CAMERA",
    }
    normalized = aliases.get(normalized, normalized)
    allowed_actions = {
        "android.media.action.IMAGE_CAPTURE",
        "android.media.action.STILL_IMAGE_CAMERA",
    }
    if normalized not in allowed_actions:
        raise ValueError("Unsupported Android intent action.")
    result = run_root_command(
        f"cmd package resolve-activity --brief -a {normalized}"
    )
    return (
        f"Android intent resolution (read-only): {normalized}\n"
        f"{result}\n"
        "Intent was resolved only; it was not launched and no device state was modified."
    )


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
    """Discover camera-related Android mechanisms without launching or controlling the camera."""
    return discover_android_mechanisms("control the phone camera")

def inspect_android_ui() -> str:
    """Inspect the current foreground Android UI hierarchy without interacting with it."""
    result = run_root_command("uiautomator dump /dev/tty")
    return (
        "Android UI inspection (read-only):\n"
        f"{result}\n"
        "UI was inspected only; no interaction or device state change was performed."
    )


def discover_android_mechanisms(request: str) -> str:
    """Discover safe, read-only Android mechanisms that may implement a missing capability."""
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Request cannot be empty.")

    requested = request.strip()
    words = [
        word for word in re.findall(r"[a-z0-9_]+", requested.lower())
        if len(word) >= 4
        and word not in {
            "control", "phone", "device", "android", "using", "with",
            "from", "that", "this", "have", "need", "capability",
        }
    ]

    results = [f"Requested capability: {requested}"]
    for executable in ("am", "cmd", "dumpsys", "pm", "uiautomator"):
        results.append(f"{executable}: {find_executable(executable)}")

    try:
        services = run_root_command("dumpsys -l")
    except (RuntimeError, ValueError) as exc:
        results.append(f"Android service discovery unavailable: {exc}")
    else:
        lines = services.splitlines()
        candidates = [
            line.strip()
            for line in lines
            if line.strip() and any(word in line.lower() for word in words)
        ]
        if candidates:
            results.append("Candidate Android services:\n" + "\n".join(candidates[:20]))
        else:
            results.append(
                "Candidate Android services: none matched the request terms. "
                "The capability may require an intent, UI, executable, or another IPC mechanism."
            )

    return (
        "Android mechanism discovery (read-only):\n"
        + "\n".join(results)
        + "\nNo action was performed and no device state was modified."
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

    try:
        parsed_arguments = json.loads(implementation_args.strip()) if implementation_args.strip() else {}
    except json.JSONDecodeError as exc:
        return f"Extension not applied: implementation_args is not valid JSON: {exc}"
    if not isinstance(parsed_arguments, dict):
        return "Extension not applied: implementation_args must decode to a JSON object."

    try:
        primitive_signature.bind(**parsed_arguments)
    except TypeError as exc:
        return (
            f"Extension not applied: arguments do not match existing primitive "
            f"'{target_name}': {exc}"
        )

    original = target.read_text(encoding="utf-8")
    try:
        tree = ast.parse(original, filename=relative)
    except SyntaxError as exc:
        return f"Extension not applied: existing source is invalid Python: {exc}"

    existing_functions = {
        node.name for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if proposed in existing_functions:
        return f"Extension not applied: capability function '{proposed}' already exists."

    declaration_marker = "TOOL_DECLARATIONS = ["
    handler_marker = "TOOL_HANDLERS: dict[str, Callable[..., str]] = {"

    # Generate the wrapper from an AST so model-supplied text cannot corrupt Python syntax.
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

    passed, verification = _run_extension_test_suite()
    if not passed:
        try:
            target.write_text(original, encoding="utf-8")
        except OSError as exc:
            return f"Extension transaction failed and rollback failed for {relative}: {exc}\n{verification}"
        return f"Extension rolled back: {verification}"

    return (
        f"Edited {relative}\n"
        "Extension status: source edit applied and transaction committed.\n"
        f"{verification}\n"
        "Real-device verification status: not yet verified; do not expose the new capability until the device test passes."
    )

def self_test() -> str:
    """Run a small deterministic health check of Nova's local execution substrate."""
    checks = []
    failures = []

    def check(name: str, condition: bool) -> None:
        if condition:
            checks.append(name)
        else:
            failures.append(name)

    try:
        check("calculator", calculator("2 + 3 * 4") == "14")
    except Exception:
        failures.append("calculator")

    try:
        value = current_datetime()
        dt.datetime.fromisoformat(value)
        check("datetime", True)
    except Exception:
        failures.append("datetime")

    try:
        check("filesystem_root", path_exists(".") == "true")
    except Exception:
        failures.append("filesystem_root")

    try:
        discovered = find_executable(Path(os.sys.executable).name)
        check("executable_discovery", discovered.startswith("Executable: "))
    except Exception:
        failures.append("executable_discovery")

    try:
        diagnosis = diagnose_command_failure("missing", "command not found")
        check("failure_diagnosis", "find_executable" in diagnosis)
    except Exception:
        failures.append("failure_diagnosis")

    total = len(checks) + len(failures)
    if failures:
        return f"Self-test: FAIL ({len(checks)}/{total} passed)\nFailed: {', '.join(failures)}"
    return f"Self-test: PASS ({len(checks)}/{total} checks passed)"


_RUN_COMMAND_ALLOWED = {
    "pwd": {()},
    "python": {("--version",), ("-V",)},
    "python3": {("--version",), ("-V",)},
    "git": {("--version",), ("status",)},
    "uname": {("-a",)},
    "whoami": {()},
    "id": {()},
}
_RUN_COMMAND_TIMEOUT_SECONDS = 5
_MAX_COMMAND_OUTPUT_BYTES = 4096
_ROOT_COMMAND_TIMEOUT_SECONDS = 5
_ROOT_COMMAND_OUTPUT_BYTES = 4096

_ROOT_DIAGNOSTIC_PATTERNS = (
    re.compile(r"^command\s+-v\s+[^\s]+$"),
    re.compile(r"^which\s+[^\s]+$"),
    re.compile(r"^readlink\s+-f\s+[^\s]+$"),
    re.compile(r"^ls(?:\s+-[A-Za-z]+)?(?:\s+[^;&|$]+)?$"),
    re.compile(r"^find\s+[^;&|$]+$"),
    re.compile(r"^getprop(?:\s+[^;&|$]+)?$"),
    re.compile(r"^dumpsys(?:\s+[A-Za-z0-9_.-]+(?:\s+[^;&|$]+)?)?$"),
    re.compile(r"^cmd\s+package\s+resolve-activity\s+--brief\s+-a\s+android\.media\.action\.IMAGE_CAPTURE$"),
    re.compile(r"^cmd\s+package\s+resolve-activity\s+--brief\s+-a\s+android\.media\.action\.STILL_IMAGE_CAMERA$"),
    re.compile(r"^uiautomator\s+dump\s+/dev/tty$"),
    re.compile(r"^settings\s+get\s+(?:global|system|secure)\s+[A-Za-z0-9_.-]+$"),
    re.compile(r"^(?:id|whoami|pwd)$"),
)



_EXECUTABLE_SEARCH_PATHS = (
    "/system/bin",
    "/system/xbin",
    "/vendor/bin",
    "/product/bin",
    "/odm/bin",
    "/data/data/com.termux/files/usr/bin",
)


def find_executable(name: str) -> str:
    """Find an executable in PATH and common Android executable directories."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Executable name cannot be empty.")
    candidate = name.strip()
    if any(char in candidate for char in ("\n", "\r", "\x00", ";", "|", "&")):
        raise ValueError("Executable name contains unsupported characters.")
    if "/" in candidate:
        path = os.path.realpath(candidate)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return f"Executable: {path}"
        return f"Executable not found: {candidate}"

    found = shutil.which(candidate)
    if found:
        return f"Executable: {os.path.realpath(found)}"

    for directory in _EXECUTABLE_SEARCH_PATHS:
        path = os.path.join(directory, candidate)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return f"Executable: {path}"

    return f"Executable not found: {candidate}"

def diagnose_command_failure(command: str, error: str) -> str:
    """Classify a failed command and recommend the safest next diagnostic step."""
    if not isinstance(command, str) or not command.strip():
        raise ValueError("Command cannot be empty.")
    if not isinstance(error, str) or not error.strip():
        raise ValueError("Error output cannot be empty.")
    text = error.strip().lower()
    if "command is not allowed" in text or "not allowed:" in text:
        return "Diagnosis: command is blocked by Nova's normal execution policy. Next: discover the executable and use the narrowest approved privileged workflow when the command is a safe Android diagnostic."
    if any(term in text for term in ("not found", "no such file or directory", "command not found")):
        return "Diagnosis: executable or path not found. Next: use find_executable for the command name or inspect the required path."
    if any(term in text for term in ("permission denied", "operation not permitted", "access denied")):
        return "Diagnosis: permission denied. Next: use Nova's manual su workflow and run a bounded root diagnostic if the operation requires privilege."
    if any(term in text for term in ("timed out", "timeout", "timedout")):
        return "Diagnosis: command timed out. Next: retry once if the operation may be transient; otherwise inspect the command and environment before retrying."
    if any(term in text for term in ("failed transaction", "service unavailable", "binder", "cannot connect to")):
        return "Diagnosis: Android service or IPC failure. Next: inspect the relevant service with run_root_command and choose an alternate mechanism if needed."
    if any(term in text for term in ("invalid argument", "invalid option", "usage:", "unknown option", "bad argument")):
        return "Diagnosis: command arguments are invalid. Next: inspect the command's supported syntax before retrying."
    return "Diagnosis: cause is unknown from the supplied error. Next: inspect stderr and environment, then use the narrowest relevant diagnostic tool before retrying."

def run_command(command: str) -> str:
    """Run one approved read-only command from Nova's bounded working root."""
    if not isinstance(command, str) or not command.strip():
        raise ValueError("Command cannot be empty.")
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        raise ValueError(f"Invalid command syntax: {exc}") from exc
    if not parts:
        raise ValueError("Command cannot be empty.")
    executable = Path(parts[0]).name
    if executable not in _RUN_COMMAND_ALLOWED:
        raise ValueError(f"Command is not allowed: {executable}")
    if "/" in parts[0]:
        resolved = os.path.realpath(parts[0])
        discovered = find_executable(executable)
        if discovered != f"Executable: {resolved}":
            raise ValueError(f"Executable path is not the discovered path: {parts[0]}")
    arguments = tuple(parts[1:])
    if arguments not in _RUN_COMMAND_ALLOWED[executable]:
        raise ValueError(f"Arguments are not allowed for {executable}.")
    try:
        completed = subprocess.run(
            parts,
            cwd=_filesystem_root(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=_RUN_COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Command timed out after {_RUN_COMMAND_TIMEOUT_SECONDS} seconds.") from exc
    except OSError as exc:
        raise RuntimeError(f"Command failed to start: {exc}") from exc

    def trim_output(value: str) -> str:
        encoded = value.encode("utf-8", errors="replace")
        if len(encoded) <= _MAX_COMMAND_OUTPUT_BYTES:
            return value.rstrip()
        return encoded[:_MAX_COMMAND_OUTPUT_BYTES].decode("utf-8", errors="ignore").rstrip() + "\n[output truncated]"

    stdout = trim_output(completed.stdout)
    stderr = trim_output(completed.stderr)
    result = f"Exit code: {completed.returncode}"
    if stdout:
        result += f"\nstdout:\n{stdout}"
    if stderr:
        result += f"\nstderr:\n{stderr}"
    return result


def _run_bounded_root_action(command: str) -> str:
    """Run one explicitly allowlisted Android action inside a root shell."""
    allowed_commands = {
        "input keyevent 3",
        "input keyevent 4",
        "input keyevent 25",
        "input keyevent 27",
        "am start -a android.media.action.IMAGE_CAPTURE",
        "am start -a android.media.action.STILL_IMAGE_CAMERA",
    }
    if command not in allowed_commands:
        raise ValueError("Root action is not allowed.")
    try:
        completed = subprocess.run(
            ["su"],
            input=command + "\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=_ROOT_COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Root action timed out after {_ROOT_COMMAND_TIMEOUT_SECONDS} seconds.") from exc
    except OSError as exc:
        raise RuntimeError(f"Root action failed to start: {exc}") from exc

    stdout = (completed.stdout or "").encode("utf-8", errors="replace")[:_ROOT_COMMAND_OUTPUT_BYTES].decode("utf-8", errors="ignore").rstrip()
    stderr = (completed.stderr or "").encode("utf-8", errors="replace")[:_ROOT_COMMAND_OUTPUT_BYTES].decode("utf-8", errors="ignore").rstrip()
    result = f"Exit code: {completed.returncode}"
    if stdout:
        result += f"\nstdout:\n{stdout}"
    if stderr:
        result += f"\nstderr:\n{stderr}"
    return result


def _dump_camera_ui_hierarchy() -> str:
    """Dump the foreground Android UI hierarchy through a bounded temporary file."""
    path = "/data/local/tmp/nova_camera_ui.xml"
    dump_command = f"uiautomator dump {path}"
    read_command = f"cat {path}"
    cleanup_command = f"rm -f {path}"
    try:
        completed = subprocess.run(
            ["su"],
            input=dump_command + "\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=8,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Camera UI hierarchy dump timed out after 8 seconds.") from exc
    except OSError as exc:
        raise RuntimeError(f"Camera UI hierarchy dump failed to start: {exc}") from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(
            "Camera UI hierarchy dump failed"
            + (f": {detail}" if detail else ".")
        )

    try:
        completed = subprocess.run(
            ["su"],
            input=read_command + "\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Camera UI hierarchy read timed out after 5 seconds.") from exc
    except OSError as exc:
        raise RuntimeError(f"Camera UI hierarchy read failed to start: {exc}") from exc
    finally:
        try:
            subprocess.run(
                ["su"],
                input=cleanup_command + "\n",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(
            "Camera UI hierarchy read failed"
            + (f": {detail}" if detail else ".")
        )

    output = (completed.stdout or "").encode("utf-8", errors="replace")
    if len(output) > _ROOT_COMMAND_OUTPUT_BYTES:
        output = output[:_ROOT_COMMAND_OUTPUT_BYTES] + b"\n[output truncated]"
    return output.decode("utf-8", errors="ignore").rstrip()


def run_root_command(command: str) -> str:
    """Run one bounded read-only diagnostic command inside a root shell."""
    if not isinstance(command, str) or not command.strip():
        raise ValueError("Command cannot be empty.")
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        raise ValueError(f"Invalid command syntax: {exc}") from exc
    normalized = " ".join(parts)
    if not parts or not any(pattern.fullmatch(normalized) for pattern in _ROOT_DIAGNOSTIC_PATTERNS):
        raise ValueError("Root command is not allowed. Use a bounded read-only diagnostic command.")
    try:
        completed = subprocess.run(
            ["su"],
            input=normalized + "\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=_ROOT_COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Root command timed out after {_ROOT_COMMAND_TIMEOUT_SECONDS} seconds.") from exc
    except OSError as exc:
        raise RuntimeError(f"Root command failed to start: {exc}") from exc

    def trim_output(value: str) -> str:
        encoded = (value or "").encode("utf-8", errors="replace")
        if len(encoded) <= _ROOT_COMMAND_OUTPUT_BYTES:
            return (value or "").rstrip()
        return encoded[:_ROOT_COMMAND_OUTPUT_BYTES].decode("utf-8", errors="ignore").rstrip() + "\n[output truncated]"

    stdout = trim_output(completed.stdout)
    stderr = trim_output(completed.stderr)
    result = f"Exit code: {completed.returncode}"
    if stdout:
        result += f"\nstdout:\n{stdout}"
    if stderr:
        result += f"\nstderr:\n{stderr}"
    return result


def verify_command_result(result: str, expected: str) -> str:
    """Verify that a command result contains the expected text."""
    if not isinstance(result, str) or not result.strip():
        raise ValueError("Command result cannot be empty.")
    if not isinstance(expected, str) or not expected.strip():
        raise ValueError("Expected text cannot be empty.")
    if expected in result:
        return f"Verification: passed. Expected text found: {expected}"
    return f"Verification: failed. Expected text not found: {expected}"


def retry_command(command: str) -> str:
    """Run one approved command and retry it at most once after a failed result."""
    if not isinstance(command, str) or not command.strip():
        raise ValueError("Command cannot be empty.")
    try:
        first_result = run_command(command)
    except RuntimeError as exc:
        if "timed out" not in str(exc).lower():
            raise
        first_result = f"Tool error: {exc}"
    if first_result.startswith("Exit code: 0"):
        return "Attempts: 1\n" + first_result
    try:
        second_result = run_command(command)
    except RuntimeError as exc:
        second_result = f"Tool error: {exc}"
    return "Attempts: 2\n" + second_result



def recover_command(command: str) -> str:
    """Execute an approved command and apply one safe, diagnostic recovery step."""
    if not isinstance(command, str) or not command.strip():
        raise ValueError("Command cannot be empty.")
    try:
        first_result = run_command(command)
    except (RuntimeError, ValueError) as exc:
        first_result = f"Tool error: {exc}"

    if first_result.startswith("Exit code: 0"):
        return "Recovery: none needed.\nAttempts: 1\n" + first_result

    diagnosis = diagnose_command_failure(command, first_result)
    lowered = first_result.lower()

    if "timed out" in lowered:
        try:
            retry_result = run_command(command)
        except (RuntimeError, ValueError) as exc:
            retry_result = f"Tool error: {exc}"
        return diagnosis + "\nAttempts: 2\n" + retry_result

    parts = shlex.split(command)
    executable = Path(parts[0]).name
    if any(term in lowered for term in (
        "not found",
        "no such file or directory",
        "command not found",
        "command is not allowed",
    )):
        discovered = find_executable(executable)
        if discovered.startswith("Executable: "):
            discovered_path = discovered.removeprefix("Executable: ")
            root_safe = any(
                pattern.fullmatch(command.strip())
                for pattern in _ROOT_DIAGNOSTIC_PATTERNS
            )
            if root_safe:
                try:
                    root_result = run_root_command(command)
                except (RuntimeError, ValueError) as exc:
                    if command.strip() == "dumpsys" and "timed out" in str(exc).lower():
                        try:
                            root_result = run_root_command("dumpsys -l")
                        except (RuntimeError, ValueError) as retry_exc:
                            root_result = f"Tool error: {retry_exc}"
                        if root_result.startswith("Exit code: 0"):
                            return diagnosis + "\nRecovery: bare dumpsys was unbounded; adapted to the bounded manual-su service-list diagnostic and command succeeded.\n" + root_result
                        return diagnosis + "\nRecovery: bare dumpsys was unbounded; bounded manual-su diagnostic also failed.\n" + root_result
                    root_result = f"Tool error: {exc}"
                if root_result.startswith("Exit code: 0"):
                    return diagnosis + "\nRecovery: executable discovered; used the manual-su root workflow and command succeeded.\n" + root_result
                return diagnosis + "\nRecovery: executable discovered; root workflow attempted but command failed.\n" + root_result

            recovered_command = " ".join(
                [shlex.quote(discovered_path), *(shlex.quote(part) for part in parts[1:])]
            )
            try:
                recovered_result = run_command(recovered_command)
            except (RuntimeError, ValueError) as exc:
                recovered_result = f"Recovery execution failed: {exc}"
            if recovered_result.startswith("Exit code: 0"):
                return diagnosis + "\nRecovery: executable path discovered and command succeeded.\n" + recovered_result
            return diagnosis + "\nRecovery: executable path discovered but corrected command failed.\n" + recovered_result
        return diagnosis + "\n" + discovered

    return diagnosis + "\nRecovery: no automatic retry performed."

def current_datetime() -> str:
    """Return the device's current local date and time."""
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def get_system_info() -> str:
    """Return basic runtime and platform information for the device."""
    return (
        f"OS: {platform.system()} {platform.release()}\n"
        f"Architecture: {platform.machine()}\n"
        f"Python: {platform.python_version()}"
    )


def get_hostname() -> str:
    """Return the device hostname."""
    return socket.gethostname()


def get_network_addresses() -> str:
    """Return unique IP addresses resolved for the local device hostname."""
    hostname = socket.gethostname()
    try:
        records = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise RuntimeError("Network addresses are unavailable.") from exc
    addresses = []
    for record in records:
        address = record[4][0]
        if address not in addresses:
            addresses.append(address)
    return "\n".join(addresses) if addresses else "(no network addresses)"


def get_network_interfaces() -> str:
    """Return local network interface names and their operational state."""
    interfaces = []
    net_root = Path("/sys/class/net")
    if net_root.is_dir():
        try:
            entries = sorted(net_root.iterdir(), key=lambda item: item.name)
        except OSError:
            entries = []
        for entry in entries:
            try:
                state = (entry / "operstate").read_text(encoding="utf-8").strip() or "unknown"
            except OSError:
                state = "unknown"
            interfaces.append(f"{entry.name}: {state}")
    if not interfaces:
        try:
            for _, name in socket.if_nameindex():
                if name:
                    interfaces.append(f"{name}: unknown")
        except OSError:
            pass
    if not interfaces:
        proc_net = Path("/proc/net/dev")
        if proc_net.is_file():
            try:
                for line in proc_net.read_text(encoding="utf-8").splitlines()[2:]:
                    if ":" in line:
                        name = line.split(":", 1)[0].strip()
                        if name:
                            interfaces.append(f"{name}: unknown")
            except OSError:
                pass
    if not interfaces:
        interfaces.append("lo: unknown")
    return "\n".join(interfaces)


def get_wifi_status() -> str:
    """Return the Android Wi-Fi radio state."""
    commands = (
        "/system/bin/cmd wifi status",
        "/system/bin/dumpsys wifi",
    )
    try:
        for command in commands:
            result = subprocess.run(
                ["su"],
                input=command + "\n",
                capture_output=True,
                text=True,
                check=False,
            )
            output = (result.stdout or "") + "\n" + (getattr(result, "stderr", "") or "")
            lowered = output.lower()
            if re.search(r"\bwi-?fi\s+(?:is\s+)?enabled\b|\bstate\s*[:=]\s*enabled\b", lowered):
                return "Wi-Fi: Enabled"
            if re.search(r"\bwi-?fi\s+(?:is\s+)?disabled\b|\bstate\s*[:=]\s*disabled\b", lowered):
                return "Wi-Fi: Disabled"
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        raise RuntimeError("Wi-Fi status is unavailable.") from exc
    raise RuntimeError("Wi-Fi status is unavailable.")




def get_airplane_mode() -> str:
    """Return whether Android airplane mode is currently enabled or disabled."""
    commands = (
        "/system/bin/settings get global airplane_mode_on",
        "/system/bin/settings get system airplane_mode_on",
        "/system/bin/settings get secure airplane_mode_on",
        "/system/bin/dumpsys wifi",
    )
    try:
        for command in commands:
            result = subprocess.run(
                ["su"],
                input=command + "\n",
                capture_output=True,
                text=True,
                check=False,
            )
            output = (result.stdout or "") + "\n" + (result.stderr or "")
            stripped = output.strip()
            if stripped == "1":
                return "Airplane mode: Enabled"
            if stripped == "0":
                return "Airplane mode: Disabled"
            match = re.search(r"(?im)\\bAirplaneModeOn\\s+(true|false)\\b", output)
            if match:
                return "Airplane mode: " + ("Enabled" if match.group(1).lower() == "true" else "Disabled")
            match = re.search(
                r"(?im)\\b(?:mAirplaneModeOn|airplaneMode|airplane_mode_on)\\s*[:=]\\s*(true|false|1|0)\\b",
                output,
            )
            if match:
                value = match.group(1).lower()
                return "Airplane mode: " + ("Enabled" if value in {"true", "1"} else "Disabled")
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        raise RuntimeError("Airplane mode status is unavailable.") from exc
    raise RuntimeError("Airplane mode status is unavailable.")

def get_bluetooth_status() -> str:
    """Return the Android Bluetooth radio state."""
    commands = (
        "/system/bin/settings get global bluetooth_on",
        "/system/bin/dumpsys bluetooth_manager",
    )
    try:
        for command in commands:
            result = subprocess.run(
                ["su", "-c", command],
                capture_output=True,
                text=True,
                check=False,
            )
            stdout = (result.stdout or "").replace("\\n", "\n")
            output = stdout + "\n" + (getattr(result, "stderr", "") or "")
            if re.fullmatch(r"\s*1\s*", stdout):
                return "Bluetooth: Enabled"
            if re.fullmatch(r"\s*0\s*", stdout):
                return "Bluetooth: Disabled"
            lowered = output.lower()
            if re.search(r"\b(?:enabled|on)\b", lowered) and "bluetooth" in lowered:
                return "Bluetooth: Enabled"
            if re.search(r"\b(?:disabled|off)\b", lowered) and "bluetooth" in lowered:
                return "Bluetooth: Disabled"
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        raise RuntimeError("Bluetooth status is unavailable.") from exc
    raise RuntimeError("Bluetooth status is unavailable.")


def get_cpu_count() -> str:
    """Return the number of logical CPUs visible to the runtime."""
    count = os.cpu_count()
    if count is None:
        raise RuntimeError("CPU count is unavailable.")
    return str(count)


def get_load_average() -> str:
    """Return the 1, 5, and 15 minute system load averages."""
    try:
        result = subprocess.run(
            ["uptime"],
            capture_output=True,
            text=True,
            check=True,
        )
        output = result.stdout.strip()
        marker = "load average:"
        if marker not in output:
            raise RuntimeError("System load average is unavailable.")
        values = output.split(marker, 1)[1].replace(",", " ").split()
        if len(values) < 3:
            raise RuntimeError("System load average is unavailable.")
        one, five, fifteen = (float(value) for value in values[:3])
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError) as exc:
        raise RuntimeError("System load average is unavailable.") from exc
    return f"1m: {one:.2f}\n5m: {five:.2f}\n15m: {fifteen:.2f}"



def get_system_uptime() -> str:
    """Return total system uptime in seconds."""
    try:
        seconds = time.clock_gettime(time.CLOCK_BOOTTIME)
    except (AttributeError, OSError, ValueError) as exc:
        raise RuntimeError("System uptime is unavailable.") from exc
    return f"{max(0.0, seconds):.3f} seconds"



def get_system_boot_time() -> str:
    """Return the device boot time as local ISO-8601 text."""
    try:
        uptime = time.clock_gettime(time.CLOCK_BOOTTIME)
        boot_timestamp = time.time() - max(0.0, uptime)
        boot_time = dt.datetime.fromtimestamp(boot_timestamp).astimezone()
    except (AttributeError, OSError, OverflowError, ValueError) as exc:
        raise RuntimeError("System boot time is unavailable.") from exc
    return boot_time.isoformat(timespec="seconds")

def get_system_cpu_usage() -> str:
    """Return the current aggregate system CPU usage percentage."""
    try:
        result = subprocess.run(
            ["top", "-b", "-n", "1"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        raise RuntimeError("System CPU usage is unavailable.") from exc

    for line in result.stdout.splitlines():
        match = re.search(r"(?:CPU usage|CPU):\s*([0-9]+(?:\.[0-9]+)?)%?", line, re.IGNORECASE)
        if match:
            usage = float(match.group(1))
            if 0.0 <= usage <= 100.0:
                return f"{usage:.2f}%"
        android_match = re.search(
            r"(?P<total>[0-9]+(?:\.[0-9]+)?)%cpu\s+"
            r"(?P<user>[0-9]+(?:\.[0-9]+)?)%user\s+"
            r"(?P<nice>[0-9]+(?:\.[0-9]+)?)%nice\s+"
            r"(?P<sys>[0-9]+(?:\.[0-9]+)?)%sys\s+"
            r"(?P<idle>[0-9]+(?:\.[0-9]+)?)%idle",
            line,
            re.IGNORECASE,
        )
        if android_match:
            total = float(android_match.group("total"))
            idle = float(android_match.group("idle"))
            if total > 0.0 and idle >= 0.0:
                usage = max(0.0, min(100.0, (total - idle) / total * 100.0))
                return f"{usage:.2f}%"
    raise RuntimeError("System CPU usage is unavailable.")

def get_screen_state() -> str:
    """Return whether the Android device screen is currently on or off."""
    try:
        result = subprocess.run(
            ["su", "-c", "/system/bin/dumpsys power"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        raise RuntimeError("System screen state is unavailable.") from exc

    for line in result.stdout.splitlines():
        match = re.search(r"Display Power:\s*state=(ON|OFF)", line, re.IGNORECASE)
        if match:
            return f"Screen: {match.group(1).upper()}"
    for line in result.stdout.splitlines():
        match = re.search(r"mWakefulness=(Awake|Asleep|Dreaming|Dozing)", line, re.IGNORECASE)
        if match:
            state = match.group(1).lower()
            return "Screen: ON" if state in {"awake", "dreaming"} else "Screen: OFF"
    raise RuntimeError("System screen state is unavailable.")

def get_screen_brightness() -> str:
    """Return the Android device screen brightness as a percentage."""
    commands = (
        ("/system/bin/settings get system screen_brightness", "integer"),
        ("/system/bin/settings get system screen_brightness_float", "float"),
        ("/system/bin/dumpsys power", "dumpsys"),
        ("/system/bin/dumpsys display", "dumpsys"),
    )
    try:
        for command, value_type in commands:
            result = subprocess.run(
                ["su", "-c", command],
                capture_output=True,
                text=True,
                check=False,
            )
            output = result.stdout.strip()
            if value_type == "integer" and re.fullmatch(r"\d+", output):
                brightness = int(output)
                if 0 <= brightness <= 255:
                    percentage = brightness * 100 / 255
                    return f"Brightness: {percentage:.0f}% ({brightness}/255)"
            elif value_type == "float" and re.fullmatch(r"(?:0|1)(?:\.\d+)?", output):
                brightness = float(output)
                return f"Brightness: {brightness * 100:.0f}% ({brightness:.2f})"
            elif value_type == "dumpsys":
                match = re.search(
                    r"(?im)\b(?:Display Brightness|mBrightnessState|mCachedBrightnessInfo\.brightness)\s*[=:]\s*(0(?:\.\d+)?|1(?:\.0+)?)\b",
                    output,
                )
                if match:
                    brightness = float(match.group(1))
                    return f"Brightness: {brightness * 100:.0f}% ({brightness:.2f})"
                match = re.search(
                    r"(?im)\bmScreenBrightnessFloat\s*[=:]\s*(0(?:\.\d+)?|1(?:\.0+)?)\b",
                    output,
                )
                if match:
                    brightness = float(match.group(1))
                    return f"Brightness: {brightness * 100:.0f}% ({brightness:.2f})"
                match = re.search(
                    r"(?im)\bmScreenBrightness\s*[=:]\s*(\d+)\b",
                    output,
                )
                if match:
                    brightness = int(match.group(1))
                    if 0 <= brightness <= 255:
                        return f"Brightness: {brightness * 100 / 255:.0f}% ({brightness}/255)"
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        raise RuntimeError("System screen brightness is unavailable.") from exc
    raise RuntimeError("System screen brightness is unavailable.")


def get_screen_brightness_mode() -> str:
    """Return whether Android screen brightness is automatic or manual."""
    commands = (
        ("/system/bin/settings get system screen_brightness_mode", "settings"),
        ("/system/bin/dumpsys power", "dumpsys"),
    )
    try:
        for command, value_type in commands:
            result = subprocess.run(
                ["su", "-c", command],
                capture_output=True,
                text=True,
                check=False,
            )
            output = result.stdout.strip()
            if value_type == "settings" and output in {"0", "1"}:
                return "Brightness mode: " + ("Automatic" if output == "1" else "Manual")
            if value_type == "dumpsys":
                match = re.search(
                    r"(?im)\bmScreenBrightnessModeSetting\s*[=:]\s*(0|1)\b",
                    output,
                )
                if not match:
                    match = re.search(
                        r"(?im)\bscreenBrightnessMode\s*[=:]\s*(0|1)\b",
                        output,
                    )
                if match:
                    return "Brightness mode: " + (
                        "Automatic" if match.group(1) == "1" else "Manual"
                    )
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        raise RuntimeError("System screen brightness mode is unavailable.") from exc
    raise RuntimeError("System screen brightness mode is unavailable.")


def get_screen_orientation() -> str:
    """Return the Android display orientation."""
    commands = (
        "/system/bin/dumpsys input",
        "/system/bin/dumpsys display",
    )
    names = {
        0: "Portrait",
        1: "Landscape",
        2: "Reverse portrait",
        3: "Reverse landscape",
    }
    try:
        for command in commands:
            result = subprocess.run(
                ["su", "-c", command],
                capture_output=True,
                text=True,
                check=False,
            )
            output = result.stdout
            match = re.search(r"(?im)\bSurfaceOrientation\s*[:=]\s*(0|1|2|3)\b", output)
            if not match:
                match = re.search(r"(?im)\bmDisplayRotation\s*[=:]\s*(0|1|2|3)\b", output)
            if not match:
                match = re.search(
                    r"(?im)\bViewport\s+INTERNAL:.*?\borientation=(0|1|2|3)\b",
                    output,
                )
            if match:
                return f"Screen orientation: {names[int(match.group(1))]}"
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        raise RuntimeError("System screen orientation is unavailable.") from exc
    raise RuntimeError("System screen orientation is unavailable.")


def get_screen_resolution() -> str:
    """Return the Android physical display resolution."""
    try:
        result = subprocess.run(
            ["su"],
            input="/system/bin/wm size\n",
            capture_output=True,
            text=True,
            check=False,
        )
        match = re.search(r"(?im)^Physical size:\s*(\d+)x(\d+)\s*$", result.stdout)
        if match:
            return f"Screen resolution: {match.group(1)}x{match.group(2)}"
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        raise RuntimeError("System screen resolution is unavailable.") from exc
    raise RuntimeError("System screen resolution is unavailable.")

def get_screen_density() -> str:
    """Return the Android display density in dots per inch."""
    try:
        result = subprocess.run(
            ["su"],
            input="/system/bin/wm density\n",
            capture_output=True,
            text=True,
            check=False,
        )
        output = result.stdout
        match = re.search(r"(?im)^Override density:\s*(\d+)\s*$", output)
        if not match:
            match = re.search(r"(?im)^Physical density:\s*(\d+)\s*$", output)
        if match:
            return f"Screen density: {int(match.group(1))} dpi"
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        raise RuntimeError("System screen density is unavailable.") from exc
    raise RuntimeError("System screen density is unavailable.")



def get_media_volume() -> str:
    """Return the current Android media-stream volume as a percentage."""
    try:
        result = subprocess.run(
            ["su"],
            input="/system/bin/dumpsys audio\n",
            capture_output=True,
            text=True,
            check=False,
        )
        output = (result.stdout or "") + "\n" + (getattr(result, "stderr", "") or "")
        stream_volume = re.search(
            r"(?ms)^\s*-\s*STREAM_MUSIC:\s*\n(?:(?!^\s*-\s*STREAM_).)*?\bstreamVolume:\s*(\d+)\b",
            output,
        )
        if stream_volume:
            current = int(stream_volume.group(1))
            maximum = 15
            if 0 <= current <= maximum:
                percentage = current * 100 / maximum
                return f"Media volume: {percentage:.0f}% ({current}/{maximum})"
        stream_match = re.search(
            r"(?ms)^\s*-?\s*STREAM_MUSIC(?:\(\d+\))?\s*:.*?(?=^\s*-?\s*STREAM_[A-Z_]+(?:\(\d+\))?\s*:|\Z)",
            output,
        )
        stream = stream_match.group(0) if stream_match else output
        patterns = (
            r"(?ms)\bMin:\s*(\d+)\s*Max:\s*(\d+)\s*Current:\s*(\d+)\b",
            r"(?ms)\bIndex Min:\s*(\d+).*?\bIndex Max:\s*(\d+).*?\bCurrent Index:\s*(\d+)\b",
            r"(?ms)\bMin:\s*(\d+).*?\bMax:\s*(\d+).*?\bCurrent(?: Index)?:\s*(\d+)\b",
        )
        for pattern in patterns:
            match = re.search(pattern, stream)
            if match:
                minimum, maximum, current = (int(value) for value in match.groups())
                if maximum > minimum and minimum <= current <= maximum:
                    percentage = (current - minimum) * 100 / (maximum - minimum)
                    return f"Media volume: {percentage:.0f}% ({current}/{maximum})"
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        raise RuntimeError("Android media volume is unavailable.") from exc
    raise RuntimeError("Android media volume is unavailable.")


def get_screen_refresh_rate() -> str:
    """Return the Android display refresh rate in Hz."""
    try:
        result = subprocess.run(
            ["su", "-c", "/system/bin/dumpsys display"],
            capture_output=True,
            text=True,
            check=False,
        )
        output = result.stdout
        patterns = (
            r"(?im)\bmRefreshRate\s*[=:]\s*(\d+(?:\.\d+)?)",
            r"(?im)\brefreshRate\s*[=:]\s*(\d+(?:\.\d+)?)",
            r"(?im)\bRefreshRate\s*[=:]\s*(\d+(?:\.\d+)?)",
        )
        for pattern in patterns:
            match = re.search(pattern, output)
            if match:
                return f"Screen refresh rate: {float(match.group(1)):g} Hz"
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        raise RuntimeError("System screen refresh rate is unavailable.") from exc
    raise RuntimeError("System screen refresh rate is unavailable.")


def get_screen_timeout() -> str:
    """Return the Android screen-off timeout."""
    commands = (
        ("/system/bin/settings get system screen_off_timeout", "settings"),
        ("/system/bin/dumpsys power", "dumpsys"),
    )
    try:
        for command, value_type in commands:
            result = subprocess.run(
                ["su", "-c", command],
                capture_output=True,
                text=True,
                check=False,
            )
            output = result.stdout.strip()
            if value_type == "settings" and re.fullmatch(r"\d+", output):
                timeout_ms = int(output)
                if timeout_ms >= 0:
                    return _format_screen_timeout(timeout_ms)
            elif value_type == "dumpsys":
                match = re.search(
                    r"(?im)\bmScreenOffTimeoutSetting\s*[=:]\s*(\d+)\b",
                    output,
                )
                if not match:
                    match = re.search(
                        r"(?im)\bscreenOffTimeout\s*[=:]\s*(\d+)\b",
                        output,
                    )
                if match:
                    return _format_screen_timeout(int(match.group(1)))
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        raise RuntimeError("System screen timeout is unavailable.") from exc
    raise RuntimeError("System screen timeout is unavailable.")


def _format_screen_timeout(timeout_ms: int) -> str:
    total_seconds = max(0, timeout_ms) // 1000
    if total_seconds < 60:
        return f"Screen timeout: {total_seconds} seconds ({timeout_ms} ms)"
    minutes, seconds = divmod(total_seconds, 60)
    if seconds:
        return f"Screen timeout: {minutes}m {seconds}s ({timeout_ms} ms)"
    return f"Screen timeout: {minutes} minutes ({timeout_ms} ms)"


def get_system_battery_status() -> str:
    """Return the Android device battery level, status, health, temperature, and power source."""
    try:
        dumpsys = shutil.which("dumpsys") or "/system/bin/dumpsys"
        result = subprocess.run(
            ["su", "-c", f"{dumpsys} battery"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        raise RuntimeError("System battery status is unavailable.") from exc

    values = {}
    for line in result.stdout.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip().lower()] = value.strip()

    level = values.get("level")
    scale = values.get("scale")
    status = values.get("status")
    health = values.get("health")
    temperature = values.get("temperature")
    voltage = values.get("voltage")

    if not level or not scale or not level.isdigit() or not scale.isdigit() or int(scale) <= 0:
        raise RuntimeError("System battery status is unavailable.")

    status_names = {
        "1": "Unknown",
        "2": "Charging",
        "3": "Discharging",
        "4": "Not charging",
        "5": "Full",
    }
    health_names = {
        "1": "Unknown",
        "2": "Good",
        "3": "Overheat",
        "4": "Dead",
        "5": "Over voltage",
        "6": "Unspecified failure",
        "7": "Cold",
    }

    parts = [
        f"Level: {min(100, max(0, int(level) * 100 // int(scale)))}%",
        f"Status: {status_names.get(status, status or 'Unknown')}",
        f"Health: {health_names.get(health, health or 'Unknown')}",
    ]
    if temperature and re.fullmatch(r"-?\d+", temperature):
        parts.append(f"Temperature: {int(temperature) / 10:.1f}°C")
    if voltage and voltage.isdigit():
        parts.append(f"Voltage: {int(voltage) / 1000:.3f} V")

    sources = []
    for key, label in (
        ("ac powered", "AC"),
        ("usb powered", "USB"),
        ("wireless powered", "Wireless"),
    ):
        if values.get(key, "").lower() == "true":
            sources.append(label)
    parts.append(f"Power source: {', '.join(sources) if sources else 'Battery'}")
    return "\n".join(parts)


def get_system_swap_usage() -> str:
    """Return total, used, and free system swap in bytes."""
    try:
        result = subprocess.run(
            ["cat", "/proc/meminfo"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        raise RuntimeError("System swap usage is unavailable.") from exc
    values = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].rstrip(":") in {"SwapTotal", "SwapFree"} and parts[1].isdigit():
            values[parts[0].rstrip(":")] = int(parts[1]) * 1024
    if "SwapTotal" not in values or "SwapFree" not in values:
        raise RuntimeError("System swap usage is unavailable.")
    total = values["SwapTotal"]
    free = min(total, values["SwapFree"])
    used = max(0, total - free)
    return f"Total: {total} bytes\nUsed: {used} bytes\nFree: {free} bytes"

def get_memory_usage() -> str:
    """Return the current Nova process resident memory usage in bytes."""
    status = Path("/proc/self/status")
    if status.is_file():
        for line in status.read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    return str(int(parts[1]) * 1024)
    raise RuntimeError("Process memory usage is unavailable.")



def get_system_memory_usage() -> str:
    """Return total, available, and used system memory in bytes."""
    try:
        result = subprocess.run(
            ["cat", "/proc/meminfo"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        raise RuntimeError("System memory usage is unavailable.") from exc
    values = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].rstrip(":") in {"MemTotal", "MemAvailable"} and parts[1].isdigit():
            values[parts[0].rstrip(":")] = int(parts[1]) * 1024
    if "MemTotal" not in values or "MemAvailable" not in values:
        raise RuntimeError("System memory usage is unavailable.")
    total = values["MemTotal"]
    available = values["MemAvailable"]
    used = max(0, total - available)
    return f"Total: {total} bytes\nUsed: {used} bytes\nAvailable: {available} bytes"

def get_temp_directory() -> str:
    """Return the operating system temporary directory used by Nova."""
    return tempfile.gettempdir()


def get_home_directory() -> str:
    """Return the home directory used by Nova."""
    return str(Path.home())


def get_process_uptime() -> str:
    """Return Nova's current process uptime in seconds."""
    status = Path("/proc/self/stat")
    if not status.is_file():
        raise RuntimeError("Process uptime is unavailable.")
    fields = status.read_text(encoding="utf-8").split()
    if len(fields) < 22:
        raise RuntimeError("Process uptime is unavailable.")
    start_ticks = int(fields[21])
    clock_ticks = os.sysconf("SC_CLK_TCK")
    if clock_ticks <= 0:
        raise RuntimeError("Process clock tick rate is unavailable.")
    uptime = (time.monotonic_ns() / 1_000_000_000) - (start_ticks / clock_ticks)
    return f"{max(0.0, uptime):.3f} seconds"


def list_processes() -> str:
    """List visible Linux processes by PID and command name."""
    rows = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            name = ""
            for line in (entry / "status").read_text(encoding="utf-8").splitlines():
                if line.startswith("Name:"):
                    name = line.split(":", 1)[1].strip()
                    break
            if name:
                rows.append((int(entry.name), name))
        except (OSError, UnicodeError):
            continue
    rows.sort()
    return "\n".join(f"{pid} {name}" for pid, name in rows[:100]) or "(no visible processes)"


def get_process_status(pid: str) -> str:
    """Return basic status information for a visible Linux process."""
    if not isinstance(pid, str) or not pid.isdigit() or int(pid) <= 0:
        raise ValueError("PID must be a positive integer.")
    status = Path("/proc") / pid / "status"
    if not status.is_file():
        raise ValueError(f"Process does not exist: {pid}")
    values = {}
    try:
        for line in status.read_text(encoding="utf-8").splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            values[key] = value.strip()
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"Process status is unavailable: {pid}") from exc
    name = values.get("Name")
    state = values.get("State")
    parent = values.get("PPid")
    threads = values.get("Threads")
    memory = values.get("VmRSS")
    if not name or not state:
        raise RuntimeError(f"Process status is unavailable: {pid}")
    result = [f"PID: {pid}", f"Name: {name}", f"State: {state}"]
    if parent:
        result.append(f"Parent PID: {parent}")
    if threads:
        result.append(f"Threads: {threads}")
    if memory:
        result.append(f"Memory: {memory}")
    return "\n".join(result)


def get_process_executable(pid: str) -> str:
    """Return the executable path of a visible local process."""
    if not isinstance(pid, str) or not pid.isdigit() or int(pid) <= 0:
        raise ValueError("PID must be a positive integer.")
    executable = Path("/proc") / pid / "exe"
    if not executable.exists():
        raise ValueError(f"Process does not exist: {pid}")
    try:
        return os.readlink(executable)
    except OSError as exc:
        raise RuntimeError(f"Process executable is unavailable: {pid}") from exc


def get_process_parent_name(pid: str) -> str:
    """Return the parent process name of a visible local process."""
    if not isinstance(pid, str) or not pid.isdigit() or int(pid) <= 0:
        raise ValueError("PID must be a positive integer.")
    status = Path("/proc") / pid / "status"
    if not status.is_file():
        raise ValueError(f"Process does not exist: {pid}")
    parent_pid = None
    try:
        for line in status.read_text(encoding="utf-8").splitlines():
            if line.startswith("PPid:"):
                value = line.split(":", 1)[1].strip()
                if value.isdigit() and int(value) > 0:
                    parent_pid = value
                break
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"Parent process is unavailable: {pid}") from exc
    if parent_pid is None:
        raise RuntimeError(f"Parent process is unavailable: {pid}")
    parent_status = Path("/proc") / parent_pid / "status"
    if not parent_status.is_file():
        raise RuntimeError(f"Parent process is unavailable: {pid}")
    try:
        for line in parent_status.read_text(encoding="utf-8").splitlines():
            if line.startswith("Name:"):
                name = line.split(":", 1)[1].strip()
                if name:
                    return name
                break
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"Parent process name is unavailable: {pid}") from exc
    raise RuntimeError(f"Parent process name is unavailable: {pid}")


def get_process_nice(pid: str) -> str:
    """Return the nice value of a visible local process."""
    if not isinstance(pid, str) or not pid.isdigit() or int(pid) <= 0:
        raise ValueError("PID must be a positive integer.")
    stat_path = Path("/proc") / pid / "stat"
    if not stat_path.is_file():
        raise ValueError(f"Process does not exist: {pid}")
    try:
        raw = stat_path.read_text(encoding="utf-8")
        closing = raw.rfind(")")
        if closing < 0:
            raise RuntimeError(f"Process nice value is unavailable: {pid}")
        fields = raw[closing + 2:].split()
        if len(fields) < 16:
            raise RuntimeError(f"Process nice value is unavailable: {pid}")
        return str(int(fields[16]))
    except (OSError, UnicodeError, ValueError, IndexError) as exc:
        raise RuntimeError(f"Process nice value is unavailable: {pid}") from exc


def get_process_memory_usage(pid: str) -> str:
    """Return resident memory usage of a visible Linux process in bytes."""
    if not isinstance(pid, str) or not pid.isdigit() or int(pid) <= 0:
        raise ValueError("PID must be a positive integer.")
    status_path = Path("/proc") / pid / "status"
    if not status_path.is_file():
        raise ValueError(f"Process does not exist: {pid}")
    try:
        for line in status_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    return str(int(parts[1]) * 1024)
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(f"Process memory usage is unavailable: {pid}") from exc
    raise RuntimeError(f"Process memory usage is unavailable: {pid}")


def get_process_cpu_time(pid: str) -> str:
    """Return user, system, and total CPU time of a visible Linux process."""
    if not isinstance(pid, str) or not pid.isdigit() or int(pid) <= 0:
        raise ValueError("PID must be a positive integer.")
    stat_path = Path("/proc") / pid / "stat"
    if not stat_path.is_file():
        raise ValueError(f"Process does not exist: {pid}")
    try:
        fields = stat_path.read_text(encoding="utf-8").split()
        if len(fields) < 15:
            raise RuntimeError(f"Process CPU time is unavailable: {pid}")
        clock_ticks = os.sysconf("SC_CLK_TCK")
        if clock_ticks <= 0:
            raise RuntimeError(f"Process CPU time is unavailable: {pid}")
        user_seconds = int(fields[13]) / clock_ticks
        system_seconds = int(fields[14]) / clock_ticks
        total_seconds = user_seconds + system_seconds
        return (
            f"User: {user_seconds:.3f} seconds\n"
            f"System: {system_seconds:.3f} seconds\n"
            f"Total: {total_seconds:.3f} seconds"
        )
    except (OSError, UnicodeError, ValueError, IndexError) as exc:
        raise RuntimeError(f"Process CPU time is unavailable: {pid}") from exc


def get_process_start_time(pid: str) -> str:
    """Return the local start time of a visible Linux process as ISO-8601 text."""
    if not isinstance(pid, str) or not pid.isdigit() or int(pid) <= 0:
        raise ValueError("PID must be a positive integer.")
    stat_path = Path("/proc") / pid / "stat"
    if not stat_path.is_file():
        raise ValueError(f"Process does not exist: {pid}")
    try:
        fields = stat_path.read_text(encoding="utf-8").split()
        if len(fields) < 22:
            raise RuntimeError(f"Process start time is unavailable: {pid}")
        start_ticks = int(fields[21])
        clock_ticks = os.sysconf("SC_CLK_TCK")
        if clock_ticks <= 0:
            raise RuntimeError(f"Process start time is unavailable: {pid}")
        boottime_clock = getattr(time, "CLOCK_BOOTTIME", None)
        if boottime_clock is None:
            raise RuntimeError(f"Process start time is unavailable: {pid}")
        uptime_seconds = time.clock_gettime(boottime_clock)
        now = dt.datetime.now().astimezone()
        process_age = uptime_seconds - (start_ticks / clock_ticks)
        return (now - dt.timedelta(seconds=process_age)).isoformat(timespec="seconds")
    except (OSError, UnicodeError, ValueError, IndexError) as exc:
        raise RuntimeError(f"Process start time is unavailable: {pid}") from exc

def get_process_working_directory(pid: str) -> str:
    """Return the working directory of a visible local process."""
    if not isinstance(pid, str) or not pid.isdigit() or int(pid) <= 0:
        raise ValueError("PID must be a positive integer.")
    working_directory = Path("/proc") / pid / "cwd"
    if not working_directory.exists():
        raise ValueError(f"Process does not exist: {pid}")
    try:
        return os.readlink(working_directory)
    except OSError as exc:
        raise RuntimeError(f"Process working directory is unavailable: {pid}") from exc


def get_process_command_line(pid: str) -> str:
    """Return the command line of a visible local process."""
    if not isinstance(pid, str) or not pid.isdigit() or int(pid) <= 0:
        raise ValueError("PID must be a positive integer.")
    cmdline = Path("/proc") / pid / "cmdline"
    if not cmdline.is_file():
        raise ValueError(f"Process does not exist: {pid}")
    try:
        raw = cmdline.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"Process command line is unavailable: {pid}") from exc
    if not raw:
        raise RuntimeError(f"Process command line is unavailable: {pid}")
    command = " ".join(part for part in raw.decode(errors="replace").split("\\x00") if part)
    return command or f"PID: {pid}"


def get_process_thread_count() -> str:
    """Return the number of threads in Nova's current process."""
    status = Path("/proc/self/status")
    if not status.is_file():
        raise RuntimeError("Process thread count is unavailable.")
    for line in status.read_text(encoding="utf-8").splitlines():
        if line.startswith("Threads:"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit() and int(parts[1]) > 0:
                return parts[1]
    raise RuntimeError("Process thread count is unavailable.")


def get_parent_process_id() -> str:
    """Return the parent process ID of the running Nova process."""
    return str(os.getppid())


def get_process_group_id() -> str:
    """Return the process group ID of the running Nova process."""
    return str(os.getpgrp())


def get_session_id() -> str:
    """Return the session ID of the running Nova process."""
    return str(os.getsid(0))


def get_user_id() -> str:
    """Return the real user ID of the running Nova process."""
    return str(os.getuid())


def get_umask() -> str:
    """Return Nova's process file-creation mask as four-digit octal text."""
    status = Path("/proc/self/status")
    if status.is_file():
        for line in status.read_text(encoding="utf-8").splitlines():
            if line.startswith("Umask:"):
                parts = line.split()
                if len(parts) >= 2:
                    value = parts[1]
                    if all(character in "01234567" for character in value):
                        return f"{int(value, 8):04o}"
    current = os.umask(0)
    os.umask(current)
    return f"{current:04o}"


def get_process_id() -> str:
    """Return the current Nova process ID."""
    return str(os.getpid())


def get_current_working_directory() -> str:
    """Return Nova's current working directory."""
    return os.getcwd()


def get_python_executable() -> str:
    """Return the path to the Python executable running Nova."""
    return os.path.abspath(os.sys.executable)


def _filesystem_root() -> Path:
    return Path(os.environ.get("NOVA_FILES_ROOT", os.getcwd())).expanduser().resolve()


def _safe_path(path: str) -> Path:
    root = _filesystem_root()
    target = (root / path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("Path is outside the allowed filesystem root.") from exc
    return target


def path_exists(path: str) -> str:
    """Return whether a path exists under the bounded Nova filesystem root."""
    target = _safe_path(path)
    return "true" if target.exists() else "false"


def create_directory(path: str) -> str:
    """Create a directory within the bounded Nova filesystem root."""
    target = _safe_path(path)
    if target.exists():
        raise ValueError(f"Destination already exists: {path}")
    target.mkdir(parents=True)
    return f"Created directory {target.relative_to(_filesystem_root())}"


def delete_directory(path: str) -> str:
    """Delete an empty directory within the bounded Nova filesystem root."""
    target = _safe_path(path)
    if not target.exists():
        raise ValueError(f"Directory does not exist: {path}")
    if not target.is_dir() or target.is_symlink():
        raise ValueError(f"Not a directory: {path}")
    if any(target.iterdir()):
        raise ValueError(f"Directory is not empty: {path}")
    target.rmdir()
    return f"Deleted directory {target.relative_to(_filesystem_root())}"


def get_file_info(path: str) -> str:
    """Return basic metadata for a file or directory under the bounded root."""
    target = _safe_path(path)
    if not target.exists() or target.is_symlink():
        raise ValueError(f"Path does not exist: {path}")
    kind = "directory" if target.is_dir() else "file" if target.is_file() else "other"
    size = target.stat().st_size
    relative = target.relative_to(_filesystem_root())
    return f"Path: {relative}\\nType: {kind}\\nSize: {size} bytes"


def get_file_access_time(path: str) -> str:
    """Return a file or directory's last access time as local ISO-8601 text."""
    target = _safe_path(path)
    if not target.exists() or target.is_symlink():
        raise ValueError(f"Path does not exist: {path}")
    return dt.datetime.fromtimestamp(target.stat().st_atime).astimezone().isoformat(timespec="seconds")


def get_file_modified_time(path: str) -> str:
    """Return a file or directory's last modification time as local ISO-8601 text."""
    target = _safe_path(path)
    if not target.exists() or target.is_symlink():
        raise ValueError(f"Path does not exist: {path}")
    return dt.datetime.fromtimestamp(target.stat().st_mtime).astimezone().isoformat(timespec="seconds")


def get_file_extension(path: str) -> str:
    """Return a file's lowercase extension, including the leading dot."""
    target = _safe_path(path)
    if not target.is_file() or target.is_symlink():
        raise ValueError(f"Not a regular file: {path}")
    return target.suffix.lower()


def get_file_name(path: str) -> str:
    """Return a file's base name under Nova's allowed local filesystem root."""
    target = _safe_path(path)
    if not target.exists() or target.is_symlink():
        raise ValueError(f"Path does not exist: {path}")
    return target.name


def get_file_stem(path: str) -> str:
    """Return a file's stem without its final extension."""
    target = _safe_path(path)
    if not target.is_file() or target.is_symlink():
        raise ValueError(f"Not a regular file: {path}")
    return target.stem


def get_file_permissions(path: str) -> str:
    """Return a file or directory's Unix permission mode as four-digit octal text."""
    target = _safe_path(path)
    if not target.exists() or target.is_symlink():
        raise ValueError(f"Path does not exist: {path}")
    return f"{target.stat().st_mode & 0o7777:04o}"


def get_file_parent(path: str) -> str:
    """Return a file or directory's parent path relative to Nova's filesystem root."""
    target = _safe_path(path)
    if not target.exists() or target.is_symlink():
        raise ValueError(f"Path does not exist: {path}")
    root = _filesystem_root()
    parent = target.parent
    return str(parent.relative_to(root)) if parent != root else "."


def list_directory_recursive(path: str = ".") -> str:
    """List all non-symlink files and directories recursively under the bounded root."""
    target = _safe_path(path)
    if not target.is_dir():
        raise ValueError(f"Not a directory: {path}")

    results = []
    for directory, dirnames, filenames in os.walk(target, followlinks=False):
        current_dir = _safe_path(directory)
        dirnames[:] = sorted(
            name for name in dirnames
            if not (current_dir / name).is_symlink()
        )
        for name in sorted(dirnames + filenames, key=str.casefold):
            candidate = _safe_path(str(Path(directory) / name))
            if candidate.is_symlink():
                continue
            kind = "directory" if candidate.is_dir() else "file" if candidate.is_file() else "other"
            results.append(f"{kind}: {candidate.relative_to(_filesystem_root())}")
            if len(results) >= _MAX_FIND_RESULTS:
                return "\n".join(results)
    return "\n".join(results) if results else "(empty directory)"


def move_directory(path: str, destination: str) -> str:
    """Move a real directory within the bounded Nova filesystem root."""
    source = _safe_path(path)
    target = _safe_path(destination)
    if not source.exists():
        raise ValueError(f"Directory does not exist: {path}")
    if not source.is_dir() or source.is_symlink():
        raise ValueError(f"Not a directory: {path}")
    if target.exists():
        raise ValueError(f"Destination already exists: {destination}")
    target.parent.mkdir(parents=True, exist_ok=True)
    source.rename(target)
    return f"Moved directory {source.relative_to(_filesystem_root())} to {target.relative_to(_filesystem_root())}"


def copy_directory(path: str, destination: str) -> str:
    """Copy a real directory within the bounded Nova filesystem root."""
    source = _safe_path(path)
    target = _safe_path(destination)
    if not source.exists():
        raise ValueError(f"Directory does not exist: {path}")
    if not source.is_dir() or source.is_symlink():
        raise ValueError(f"Not a directory: {path}")
    if target.exists():
        raise ValueError(f"Destination already exists: {destination}")
    if target == source or source in target.parents:
        raise ValueError("Destination cannot be inside the source directory.")
    target.mkdir(parents=True)
    for current, dirnames, filenames in os.walk(source, followlinks=False):
        current_path = Path(current)
        relative = current_path.relative_to(source)
        destination_dir = target / relative
        destination_dir.mkdir(parents=True, exist_ok=True)
        for name in dirnames:
            source_path = current_path / name
            if source_path.is_symlink():
                continue
            (destination_dir / name).mkdir(exist_ok=True)
        for name in filenames:
            source_path = current_path / name
            if source_path.is_symlink():
                continue
            (destination_dir / name).write_bytes(source_path.read_bytes())
    return f"Copied directory {source.relative_to(_filesystem_root())} to {target.relative_to(_filesystem_root())}"


def hash_file(path: str) -> str:
    """Return the SHA-256 hash of a regular file under the bounded root."""
    target = _safe_path(path)
    if not target.is_file() or target.is_symlink():
        raise ValueError(f"Not a regular file: {path}")
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_file_lines(path: str) -> str:
    """Return the number of text lines in a UTF-8 file under the bounded root."""
    target = _safe_path(path)
    if not target.is_file() or target.is_symlink():
        raise ValueError(f"Not a regular file: {path}")
    if target.stat().st_size > _MAX_READ_BYTES:
        raise ValueError(f"File is larger than {_MAX_READ_BYTES} bytes.")
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("File is not valid UTF-8 text.") from exc
    return str(len(content.splitlines()))


def get_directory_entry_count(path: str = ".") -> str:
    """Return the number of immediate non-symlink entries in a directory."""
    target = _safe_path(path)
    if not target.is_dir() or target.is_symlink():
        raise ValueError(f"Not a directory: {path}")
    return str(sum(1 for entry in target.iterdir() if not entry.is_symlink()))


def get_disk_usage(path: str = ".") -> str:
    """Return total, used, and free bytes for the filesystem containing a path."""
    target = _safe_path(path)
    if not target.exists() or target.is_symlink():
        raise ValueError(f"Path does not exist: {path}")
    usage = shutil.disk_usage(target)
    return f"Total: {usage.total} bytes\nUsed: {usage.used} bytes\nFree: {usage.free} bytes"


def get_directory_size(path: str = ".") -> str:
    """Return the total size of regular files in a directory tree under the bounded root."""
    target = _safe_path(path)
    if not target.is_dir() or target.is_symlink():
        raise ValueError(f"Not a directory: {path}")
    total = 0
    for directory, dirnames, filenames in os.walk(target, followlinks=False):
        current = _safe_path(directory)
        dirnames[:] = [name for name in dirnames if not (current / name).is_symlink()]
        for name in filenames:
            candidate = current / name
            if candidate.is_symlink():
                continue
            if candidate.is_file():
                total += candidate.stat().st_size
    return f"{total} bytes"


def list_directory(path: str = ".") -> str:
    """List entries under the bounded Nova filesystem root."""
    target = _safe_path(path)
    if not target.is_dir():
        raise ValueError(f"Not a directory: {path}")
    entries = []
    for entry in sorted(target.iterdir(), key=lambda item: item.name.lower()):
        kind = "directory" if entry.is_dir() else "file" if entry.is_file() else "other"
        entries.append(f"{kind}: {entry.name}")
    return "\n".join(entries) if entries else "(empty directory)"


def read_text_file(path: str) -> str:
    """Read a UTF-8 text file under the bounded Nova filesystem root."""
    target = _safe_path(path)
    if not target.is_file():
        raise ValueError(f"Not a file: {path}")
    if target.stat().st_size > _MAX_READ_BYTES:
        raise ValueError(f"File is larger than {_MAX_READ_BYTES} bytes.")
    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("File is not valid UTF-8 text.") from exc


def write_text_file(path: str, content: str) -> str:
    """Write UTF-8 text under the bounded Nova filesystem root."""
    target = _safe_path(path)
    if target.exists() and not target.is_file():
        raise ValueError(f"Not a file: {path}")
    data = str(content)
    encoded = data.encode("utf-8")
    if len(encoded) > _MAX_WRITE_BYTES:
        raise ValueError(f"Content is larger than {_MAX_WRITE_BYTES} bytes.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(encoded)
    return f"Wrote {len(encoded)} bytes to {target.relative_to(_filesystem_root())}"


def edit_text_file(path: str, old_text: str, new_text: str) -> str:
    """Replace exactly one occurrence of text in a UTF-8 file under the bounded root."""
    target = _safe_path(path)
    if not target.is_file() or target.is_symlink():
        raise ValueError(f"Not a regular file: {path}")
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("File is not valid UTF-8 text.") from exc
    if not old_text:
        raise ValueError("Text to replace cannot be empty.")
    count = content.count(old_text)
    if count == 0:
        raise ValueError("Text to replace was not found.")
    if count > 1:
        raise ValueError("Text to replace occurs more than once.")
    updated = content.replace(old_text, new_text, 1)
    encoded = updated.encode("utf-8")
    if len(encoded) > _MAX_WRITE_BYTES:
        raise ValueError(f"Content is larger than {_MAX_WRITE_BYTES} bytes.")
    target.write_bytes(encoded)
    return f"Edited {target.relative_to(_filesystem_root())}"


def append_text_file(path: str, content: str) -> str:
    """Append UTF-8 text to a file under the bounded Nova filesystem root."""
    target = _safe_path(path)
    if target.exists() and not target.is_file():
        raise ValueError(f"Not a file: {path}")
    data = str(content)
    encoded = data.encode("utf-8")
    if len(encoded) > _MAX_WRITE_BYTES:
        raise ValueError(f"Content is larger than {_MAX_WRITE_BYTES} bytes.")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("ab") as handle:
        handle.write(encoded)
    return f"Appended {len(encoded)} bytes to {target.relative_to(_filesystem_root())}"


def copy_file(path: str, destination: str) -> str:
    """Copy a regular file within the bounded Nova filesystem root."""
    source = _safe_path(path)
    target = _safe_path(destination)
    if not source.exists():
        raise ValueError(f"File does not exist: {path}")
    if not source.is_file() or source.is_symlink():
        raise ValueError(f"Not a regular file: {path}")
    if target.exists():
        raise ValueError(f"Destination already exists: {destination}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    return f"Copied {source.relative_to(_filesystem_root())} to {target.relative_to(_filesystem_root())}"


def move_file(path: str, destination: str) -> str:
    """Move a regular file within the bounded Nova filesystem root."""
    source = _safe_path(path)
    target = _safe_path(destination)
    if not source.exists():
        raise ValueError(f"File does not exist: {path}")
    if not source.is_file() or source.is_symlink():
        raise ValueError(f"Not a regular file: {path}")
    if target.exists():
        raise ValueError(f"Destination already exists: {destination}")
    target.parent.mkdir(parents=True, exist_ok=True)
    source.rename(target)
    return f"Moved {source.relative_to(_filesystem_root())} to {target.relative_to(_filesystem_root())}"


def delete_file(path: str) -> str:
    """Delete a regular file under the bounded Nova filesystem root."""
    target = _safe_path(path)
    if not target.exists():
        raise ValueError(f"File does not exist: {path}")
    if not target.is_file() or target.is_symlink():
        raise ValueError(f"Not a regular file: {path}")
    target.unlink()
    return f"Deleted {target.relative_to(_filesystem_root())}"


def find_files(pattern: str, path: str = ".") -> str:
    """Find files and directories by name pattern under the bounded root."""
    if not pattern:
        raise ValueError("File pattern cannot be empty.")
    target = _safe_path(path)
    if not target.is_dir():
        raise ValueError(f"Not a directory: {path}")

    results = []
    for directory, dirnames, filenames in os.walk(target, followlinks=False):
        current_dir = _safe_path(directory)
        dirnames[:] = [name for name in dirnames if not (current_dir / name).is_symlink()]
        names = sorted(dirnames + filenames, key=str.casefold)
        for name in names:
            if fnmatch.fnmatchcase(name.casefold(), pattern.casefold()):
                candidate = _safe_path(str(Path(directory) / name))
                if candidate.is_symlink():
                    continue
                results.append(str(candidate.relative_to(_filesystem_root())))
                if len(results) >= _MAX_FIND_RESULTS:
                    return "\n".join(results)
    return "\n".join(results) if results else "(no matches)"


def search_text(pattern: str, path: str = ".") -> str:
    """Find literal text matches in UTF-8 files under the bounded root."""
    if not pattern:
        raise ValueError("Search pattern cannot be empty.")
    target = _safe_path(path)
    if not target.is_dir():
        raise ValueError(f"Not a directory: {path}")

    needle = re.compile(re.escape(pattern), re.IGNORECASE)
    results = []
    for directory, dirnames, filenames in os.walk(target, followlinks=False):
        current_dir = _safe_path(directory)
        dirnames[:] = [name for name in dirnames if not (current_dir / name).is_symlink()]
        for name in sorted(filenames, key=str.casefold):
            candidate = _safe_path(str(Path(directory) / name))
            if candidate.is_symlink() or candidate.stat().st_size > _MAX_READ_BYTES:
                continue
            try:
                content = candidate.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if "\x00" in content:
                continue
            lines = content.splitlines()
            relative = candidate.relative_to(_filesystem_root())
            for line_number, line in enumerate(lines, start=1):
                if needle.search(line):
                    results.append(f"{relative}:{line_number}: {line}")
                    if len(results) >= _MAX_SEARCH_RESULTS:
                        return "\n".join(results)
    return "\n".join(results) if results else "(no matches)"


def remember_fact(key: str, value: str) -> str:
    """Placeholder handler overridden by the agent with persistent memory."""
    raise RuntimeError("Persistent memory is not configured.")


def forget_fact(key: str) -> str:
    """Placeholder handler overridden by the agent with persistent memory."""
    raise RuntimeError("Persistent memory is not configured.")


def list_memory() -> str:
    """Placeholder handler overridden by the agent with persistent memory."""
    raise RuntimeError("Persistent memory is not configured.")


GET_BLUETOOTH_STATUS_DECLARATION = {
    "name": "get_bluetooth_status",
    "description": "Get whether the Android Bluetooth radio is currently enabled or disabled.",
    "parameters": {"type": "OBJECT", "properties": {}},
}

GET_AIRPLANE_MODE_DECLARATION = {
    "name": "get_airplane_mode",
    "description": "Get whether Android airplane mode is currently enabled or disabled.",
    "parameters": {"type": "OBJECT", "properties": {}},
}

RUN_ROOT_COMMAND_DECLARATION = {
    "name": "run_root_command",
    "description": "Run one bounded read-only diagnostic command inside a root shell using Nova's manual su workflow. Use it to discover paths, inspect Android services, and diagnose privileged command failures.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "command": {"type": "STRING", "description": "Bounded read-only diagnostic command, such as command -v dumpsys, readlink -f /system/bin/dumpsys, dumpsys wifi, or settings get global airplane_mode_on."}
        },
        "required": ["command"],
    },
}

FIND_EXECUTABLE_DECLARATION = {
    "name": "find_executable",
    "description": "Find an executable by name in Nova's PATH and common Android executable directories. Use this when a command may have failed because its executable path is unknown.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "name": {"type": "STRING", "description": "Executable name such as dumpsys, python, or settings."}
        },
        "required": ["name"],
    },
}


DIAGNOSE_COMMAND_FAILURE_DECLARATION = {
    "name": "diagnose_command_failure",
    "description": "Classify a failed command and recommend the safest next diagnostic step. Use this before blindly retrying a failed operation.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "command": {"type": "STRING", "description": "The command that failed."},
            "error": {"type": "STRING", "description": "The error or stderr returned by the failed command."},
        },
        "required": ["command", "error"],
    },
}


RECOVER_COMMAND_DECLARATION = {
    "name": "recover_command",
    "description": "Execute one approved command and apply one safe diagnostic recovery step when it fails. Use this for adaptive command recovery instead of blindly retrying.",
    "parameters": {"type": "OBJECT", "properties": {
        "command": {"type": "STRING", "description": "Approved command and arguments to execute."},
    }, "required": ["command"]},
}


RETRY_COMMAND_DECLARATION = {
    "name": "retry_command",
    "description": "Run one approved command and retry it at most once after a failed result. Use this for bounded recovery instead of blindly repeating commands.",
    "parameters": {"type": "OBJECT", "properties": {
        "command": {"type": "STRING", "description": "Approved command and arguments to run."},
    }, "required": ["command"]},
}


VERIFY_COMMAND_RESULT_DECLARATION = {
    "name": "verify_command_result",
    "description": "Verify that a command result contains expected text. Use this after executing a command when success must be explicitly checked.",
    "parameters": {"type": "OBJECT", "properties": {
        "result": {"type": "STRING", "description": "The command result to verify."},
        "expected": {"type": "STRING", "description": "Exact text expected in the result."},
    }, "required": ["result", "expected"]},
}


TOOL_DECLARATIONS = [
    {
        "name": "calculator",
        "description": "Calculate basic arithmetic expressions.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "expression": {
                    "type": "STRING",
                    "description": "A basic arithmetic expression using numbers and +, -, *, /, %, and parentheses.",
                }
            },
            "required": ["expression"],
        },
    },

    {
        "name": "current_datetime",
        "description": "Get the device's current local date and time.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "discover_android_mechanisms",
        "description": "Discover safe, read-only Android executables and service candidates that may implement a missing capability. No action is performed.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "request": {"type": "STRING", "description": "The capability whose Android implementation mechanisms should be discovered."}
            },
            "required": ["request"],
        },
    },
    {
        "name": "resolve_android_intent",
        "description": "Resolve an allowlisted Android intent without launching it. Use this to discover which activity would handle a mechanism before any action is performed.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Android intent action, currently IMAGE_CAPTURE or STILL_IMAGE_CAMERA.",
                }
            },
            "required": ["action"],
        },
    },
    {
        "name": "discover_camera_control",
        "description": "Inspect Android for safe, read-only mechanisms that could control the phone camera, without performing a camera action.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "send_android_keyevent",
        "description": "Send one bounded Android key event through the manually entered root shell. Supported actions: HOME, BACK, VOLUME_DOWN, CAMERA.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "keycode": {"type": "STRING", "description": "HOME, BACK, CAMERA, or Android keycode 3, 4, or 27."}
            },
            "required": ["keycode"],
        },
    },
    {
        "name": "inspect_android_ui",
        "description": "Inspect the current foreground Android UI hierarchy using read-only diagnostics without interacting with the UI.",
        "parameters": {"type": "OBJECT", "properties": {}, "required": []},
    },
    {
        "name": "send_android_intent",
        "description": "Launch one bounded Android intent action from Nova's allowlisted action set.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Android intent action, currently IMAGE_CAPTURE or android.media.action.IMAGE_CAPTURE.",
                }
            },
            "required": ["action"],
        },
    },

    {
        "name": "self_test",
        "description": "Run a small deterministic health check of Nova's local execution substrate without modifying user data.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "capability_inventory",
        "description": "List the local tools Nova currently exposes and their purposes.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "assess_capability_gap",
        "description": "Determine whether Nova has a plausible local capability for a requested task, without inventing unsupported capabilities.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "request": {"type": "STRING", "description": "The capability the user is asking whether Nova has."}
            },
            "required": ["request"],
        },
    },
    {
        "name": "plan_capability_extension",
        "description": "Create a bounded implementation plan for a missing capability without modifying code or device state.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "request": {"type": "STRING", "description": "The missing capability to plan an extension for."}
            },
            "required": ["request"],
        },
    },
    FIND_EXECUTABLE_DECLARATION,
    DIAGNOSE_COMMAND_FAILURE_DECLARATION,
    VERIFY_COMMAND_RESULT_DECLARATION,
    RETRY_COMMAND_DECLARATION,
    RECOVER_COMMAND_DECLARATION,
    GET_BLUETOOTH_STATUS_DECLARATION,
    RUN_ROOT_COMMAND_DECLARATION,
    GET_AIRPLANE_MODE_DECLARATION,
    {
        "name": "get_wifi_status",
        "description": "Get whether the Android Wi-Fi radio is currently enabled or disabled.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "apply_capability_extension",
        "description": "Apply one bounded extension by composing an existing local tool. Nova generates the wrapper locally and never accepts model-generated Python source.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "request": {"type": "STRING", "description": "The missing capability being extended."},
                "path": {"type": "STRING", "description": "Use exactly gemini_agent/tools.py."},
                "implementation_kind": {"type": "STRING", "description": "Must be existing_tool."},
                "implementation_target": {"type": "STRING", "description": "Name of an existing tool in Nova's local TOOL_HANDLERS."},
                "implementation_args": {"type": "STRING", "description": "JSON object of arguments passed to the existing primitive."},
                "declaration_description": {"type": "STRING", "description": "Description for the new tool declaration."}
            },
            "required": ["request", "path", "implementation_kind", "implementation_target", "implementation_args", "declaration_description"],
        },
    },
    {
        "name": "get_hostname",
        "description": "Get the device hostname.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_network_addresses",
        "description": "Get unique IP addresses resolved for the local device hostname.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_load_average",
        "description": "Get the 1, 5, and 15 minute system load averages.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_system_boot_time",
        "description": "Get the device boot time as local ISO-8601 text.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_system_uptime",
        "description": "Get total system uptime in seconds.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_system_battery_status",
        "description": "Get the Android device battery level, status, health, temperature, voltage, and power source.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_screen_state",
        "description": "Get whether the Android device screen is currently on or off.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_screen_brightness",
        "description": "Get the Android device screen brightness as a percentage.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_system_cpu_usage",
        "description": "Get the current aggregate system CPU usage percentage.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_system_memory_usage",
        "description": "Get total, used, and available system memory in bytes. Call this tool with an empty JSON object: {}.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_system_swap_usage",
        "description": "Get total, used, and free system swap in bytes. Call this tool with an empty JSON object: {}.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_network_interfaces",
        "description": "List local network interface names and their operational state.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_system_info",
        "description": "Get basic operating system, architecture, and Python runtime information.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_process_nice",
        "description": "Get the Unix nice value of a visible local process.",
        "parameters": {
            "type": "OBJECT",
            "properties": {"pid": {"type": "STRING", "description": "Positive process ID to inspect."}},
            "required": ["pid"],
        },
    },
    {
        "name": "get_process_memory_usage",
        "description": "Get resident memory usage in bytes for a visible local process.",
        "parameters": {
            "type": "OBJECT",
            "properties": {"pid": {"type": "STRING", "description": "Positive process ID to inspect."}},
            "required": ["pid"],
        },
    },
    {
        "name": "get_process_cpu_time",
        "description": "Get user, system, and total CPU time of a visible local process.",
        "parameters": {
            "type": "OBJECT",
            "properties": {"pid": {"type": "STRING", "description": "Positive process ID to inspect."}},
            "required": ["pid"],
        },
    },
    {
        "name": "get_process_id",
        "description": "Get the process ID of the running Nova process.",
        "parameters": {"type": "OBJECT", "properties": {}},
      },
    {
        "name": "get_process_executable",
        "description": "Get the executable path of a visible local process.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "pid": {"type": "STRING", "description": "Positive process ID to inspect."}
            },
            "required": ["pid"],
        },
    },
      {
        "name": "get_current_working_directory",
        "description": "Get Nova's current working directory.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_python_executable",
        "description": "Get the path to the Python executable running Nova.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_cpu_count",
        "description": "Get the number of logical CPUs visible to the runtime.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_memory_usage",
        "description": "Get the current resident memory usage of the running Nova process in bytes.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_temp_directory",
        "description": "Get the operating system temporary directory used by Nova.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_home_directory",
        "description": "Get the home directory used by Nova.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_process_uptime",
        "description": "Get the current uptime of the Nova process in seconds.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_process_thread_count",
        "description": "Get the number of threads in the running Nova process.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_parent_process_id",
        "description": "Get the parent process ID of the running Nova process.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_process_group_id",
        "description": "Get the process group ID of the running Nova process.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_session_id",
        "description": "Get the session ID of the running Nova process.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_user_id",
        "description": "Get the real user ID of the running Nova process.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_umask",
        "description": "Get Nova's process file-creation mask as four-digit octal text.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "remember_fact",
        "description": "Store a durable fact about the user for future conversations.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "key": {"type": "STRING", "description": "Short fact name."},
                "value": {"type": "STRING", "description": "The value to remember."},
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "forget_fact",
        "description": "Delete a durable fact about the user from memory.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "key": {"type": "STRING", "description": "The fact name to forget."}
            },
            "required": ["key"],
        },
    },
    {
        "name": "list_memory",
        "description": "List the durable facts Nova currently remembers about the user.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_screen_brightness_mode",
        "description": "Get whether Android screen brightness is automatic or manual.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_screen_orientation",
        "description": "Get the current Android display orientation.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_screen_resolution",
        "description": "Get the Android physical display resolution.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_screen_density",
        "description": "Get the current Android display density in dots per inch.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_media_volume",
        "description": "Get the current Android media-stream volume as a percentage.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "get_screen_refresh_rate",
        "description": "Get the current Android display refresh rate in Hz.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },

    {
        "name": "get_screen_timeout",
        "description": "Get the Android screen-off timeout duration.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "path_exists",
        "description": "Check whether a file or directory exists under Nova's allowed local filesystem root.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Relative path to check."}
            },
            "required": ["path"],
        },
    },
    {
        "name": "create_directory",
        "description": "Create a directory within Nova's allowed local filesystem root.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Relative directory path to create."}
            },
            "required": ["path"],
        },
    },
    {
        "name": "delete_directory",
        "description": "Delete an empty directory under Nova's allowed local filesystem root.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Relative directory path to delete."}
            },
            "required": ["path"],
        },
    },
    {
        "name": "get_file_info",
        "description": "Get basic type and size information for a file or directory under Nova's allowed local filesystem root.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Relative path to inspect."}
            },
            "required": ["path"],
        },
    },
    {
        "name": "get_file_access_time",
        "description": "Get the last access time of a file or directory under Nova's allowed local filesystem root.",
        "parameters": {"type": "OBJECT", "properties": {"path": {"type": "STRING", "description": "Relative path to inspect."}}, "required": ["path"]},
    },
    {
        "name": "get_file_modified_time",
        "description": "Get the last modification time of a file or directory under Nova's allowed local filesystem root.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Relative path to inspect."}
            },
            "required": ["path"],
        },
    },
    {
        "name": "get_file_extension",
        "description": "Get a file's lowercase extension under Nova's allowed local filesystem root.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Relative path to the file to inspect."}
            },
            "required": ["path"],
        },
    },
    {
        "name": "get_file_name",
        "description": "Get the base name of a file or directory under Nova's allowed local filesystem root.",
        "parameters": {"type": "OBJECT", "properties": {"path": {"type": "STRING", "description": "Relative path to inspect."}}, "required": ["path"]},
    },
    {
        "name": "get_file_stem",
        "description": "Get a file's name without its final extension under Nova's allowed local filesystem root.",
        "parameters": {"type": "OBJECT", "properties": {"path": {"type": "STRING", "description": "Relative path to the file to inspect."}}, "required": ["path"]},
    },
    {
        "name": "get_file_permissions",
        "description": "Get a file or directory's Unix permission mode under Nova's allowed local filesystem root.",
        "parameters": {"type": "OBJECT", "properties": {"path": {"type": "STRING", "description": "Relative path to inspect."}}, "required": ["path"]},
    },
    {
        "name": "get_file_parent",
        "description": "Get a file or directory's parent path under Nova's allowed local filesystem root.",
        "parameters": {"type": "OBJECT", "properties": {"path": {"type": "STRING", "description": "Relative path to inspect."}}, "required": ["path"]},
    },
    {
        "name": "list_directory_recursive",
        "description": "Recursively list files and directories under Nova's allowed local filesystem root.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Relative directory path to list recursively."}
            },
        },
    },
    {
        "name": "move_directory",
        "description": "Move a directory within Nova's allowed local filesystem root.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Relative source directory path."},
                "destination": {"type": "STRING", "description": "Relative destination directory path."},
            },
            "required": ["path", "destination"],
        },
    },
    {
        "name": "copy_directory",
        "description": "Copy a directory within Nova's allowed local filesystem root.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Relative source directory path."},
                "destination": {"type": "STRING", "description": "Relative destination directory path."},
            },
            "required": ["path", "destination"],
        },
    },
    {
        "name": "hash_file",
        "description": "Calculate the SHA-256 hash of a regular file under Nova's allowed local filesystem root.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Relative path to the file to hash."}
            },
            "required": ["path"],
        },
    },
    {
        "name": "count_file_lines",
        "description": "Count the lines in a UTF-8 text file under Nova's allowed local filesystem root.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Relative path to the text file to count."}
            },
            "required": ["path"],
        },
    },
    {
        "name": "get_directory_entry_count",
        "description": "Count immediate non-symlink files and directories under Nova's allowed local filesystem root.",
        "parameters": {"type": "OBJECT", "properties": {"path": {"type": "STRING", "description": "Relative directory path to inspect."}}, "required": ["path"]},
    },
    {
        "name": "get_disk_usage",
        "description": "Get total, used, and free disk space for the filesystem containing a path.",
        "parameters": {"type": "OBJECT", "properties": {"path": {"type": "STRING", "description": "Relative path whose filesystem should be inspected."}}, "required": ["path"]},
    },
    {
        "name": "get_directory_size",
        "description": "Calculate the total size of regular files in a directory tree under Nova's allowed local filesystem root.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Relative directory path to measure."}
            },
        },
    },
    {
        "name": "list_directory",
        "description": "List files and directories under Nova's allowed local filesystem root.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Relative directory path."}
            },
        },
    },
    {
        "name": "read_text_file",
        "description": "Read a UTF-8 text file under Nova's allowed local filesystem root.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Relative path to the text file."}
            },
            "required": ["path"],
        },
    },
    {
        "name": "search_text",
        "description": "Find literal text in UTF-8 files under Nova's allowed local filesystem root.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "pattern": {"type": "STRING", "description": "Text to find, matched case-insensitively."},
                "path": {"type": "STRING", "description": "Relative directory to search."},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "write_text_file",
        "description": "Write UTF-8 text to a file under Nova's allowed local filesystem root.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Relative path to the text file."},
                "content": {"type": "STRING", "description": "UTF-8 text to write."},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_text_file",
        "description": "Replace exactly one occurrence of text in a UTF-8 file under Nova's allowed local filesystem root.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Relative path to the text file."},
                "old_text": {"type": "STRING", "description": "Exact text to replace."},
                "new_text": {"type": "STRING", "description": "Replacement text."},
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
    {
        "name": "append_text_file",
        "description": "Append UTF-8 text to a file under Nova's allowed local filesystem root.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Relative path to the text file."},
                "content": {"type": "STRING", "description": "UTF-8 text to append."},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "copy_file",
        "description": "Copy a regular file within Nova's allowed local filesystem root.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Relative path to the file to copy."},
                "destination": {"type": "STRING", "description": "Relative destination path for the copy."},
            },
            "required": ["path", "destination"],
        },
    },
    {
        "name": "move_file",
        "description": "Move a regular file within Nova's allowed local filesystem root.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Relative path to the file to move."},
                "destination": {"type": "STRING", "description": "Relative destination path for the file."},
            },
            "required": ["path", "destination"],
        },
    },
    {
        "name": "delete_file",
        "description": "Delete a regular file under Nova's allowed local filesystem root.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Relative path to the file to delete."}
            },
            "required": ["path"],
        },
    },
    {
        "name": "find_files",
        "description": "Find files and directories by name pattern under Nova's allowed local filesystem root.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "pattern": {"type": "STRING", "description": "Filename pattern such as *.txt."},
                "path": {"type": "STRING", "description": "Relative directory to search."},
            },
            "required": ["pattern"],
        },
    },

]


RECOVER_COMMAND_DECLARATION = {
    "name": "recover_command",
    "description": "Execute one approved command and apply one safe diagnostic recovery step when it fails. Use this for adaptive command recovery instead of blindly retrying.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "command": {"type": "STRING", "description": "Approved command and arguments to execute."}
        },
        "required": ["command"],
    },
}

RUN_COMMAND_DECLARATION = {
    "name": "run_command",
    "description": "Run one approved read-only command from Nova's bounded working root.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "command": {"type": "STRING", "description": "Approved command and arguments to run."}
        },
        "required": ["command"],
    },
}
LIST_PROCESSES_DECLARATION = {
    "name": "list_processes",
    "description": "List visible local processes by PID and command name.",
    "parameters": {"type": "OBJECT", "properties": {}},
}
GET_PROCESS_EXECUTABLE_DECLARATION = {
    "name": "get_process_executable",
    "description": "Get the executable path of a visible local process.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "pid": {"type": "STRING", "description": "Positive process ID to inspect."}
        },
        "required": ["pid"],
    },
}
GET_PROCESS_PARENT_NAME_DECLARATION = {
    "name": "get_process_parent_name",
    "description": "Get the parent process name of a visible local process.",
    "parameters": {
        "type": "OBJECT",
        "properties": {"pid": {"type": "STRING", "description": "Positive process ID to inspect."}},
        "required": ["pid"],
    },
}
GET_PROCESS_MEMORY_USAGE_DECLARATION = {
    "name": "get_process_memory_usage",
    "description": "Get resident memory usage in bytes for a visible local process.",
    "parameters": {"type": "OBJECT", "properties": {"pid": {"type": "STRING", "description": "Positive process ID to inspect."}}, "required": ["pid"]},
}

GET_PROCESS_NICE_DECLARATION = {
    "name": "get_process_nice",
    "description": "Get the Unix nice value of a visible local process.",
    "parameters": {
        "type": "OBJECT",
        "properties": {"pid": {"type": "STRING", "description": "Positive process ID to inspect."}},
        "required": ["pid"],
    },
}
GET_PROCESS_CPU_TIME_DECLARATION = {
    "name": "get_process_cpu_time",
    "description": "Get user, system, and total CPU time of a visible local process.",
    "parameters": {
        "type": "OBJECT",
        "properties": {"pid": {"type": "STRING", "description": "Positive process ID to inspect."}},
        "required": ["pid"],
    },
}
GET_PROCESS_START_TIME_DECLARATION = {
    "name": "get_process_start_time",
    "description": "Get the local start time of a visible local process.",
    "parameters": {
        "type": "OBJECT",
        "properties": {"pid": {"type": "STRING", "description": "Positive process ID to inspect."}},
        "required": ["pid"],
    },
}
GET_PROCESS_WORKING_DIRECTORY_DECLARATION = {
    "name": "get_process_working_directory",
    "description": "Get the working directory of a visible local process.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "pid": {"type": "STRING", "description": "Positive process ID to inspect."}
        },
        "required": ["pid"],
    },
}
GET_PROCESS_COMMAND_LINE_DECLARATION = {
    "name": "get_process_command_line",
    "description": "Get the command line of a visible local process.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "pid": {"type": "STRING", "description": "Positive process ID to inspect."}
        },
        "required": ["pid"],
    },
}

GET_WIFI_STATUS_DECLARATION = {
    "name": "get_wifi_status",
    "description": "Get whether the Android Wi-Fi radio is currently enabled or disabled.",
    "parameters": {"type": "OBJECT", "properties": {}},
}

GET_NETWORK_ADDRESSES_DECLARATION = {
    "name": "get_network_addresses",
    "description": "Get unique IP addresses resolved for the local device hostname.",
    "parameters": {"type": "OBJECT", "properties": {}},
}
GET_SYSTEM_SCREEN_STATE_DECLARATION = {
    "name": "get_screen_state",
    "description": "Get whether the Android device screen is currently on or off.",
    "parameters": {"type": "OBJECT", "properties": {}},
}
GET_SYSTEM_SCREEN_BRIGHTNESS_DECLARATION = {
    "name": "get_screen_brightness",
    "description": "Get the Android device screen brightness as a percentage.",
    "parameters": {"type": "OBJECT", "properties": {}},
}

GET_SYSTEM_SCREEN_ORIENTATION_DECLARATION = {
    "name": "get_screen_orientation",
    "description": "Get the current Android display orientation.",
    "parameters": {"type": "OBJECT", "properties": {}},
}

GET_SYSTEM_SCREEN_RESOLUTION_DECLARATION = {
    "name": "get_screen_resolution",
    "description": "Get the Android physical display resolution.",
    "parameters": {"type": "OBJECT", "properties": {}},
}

GET_SYSTEM_SCREEN_DENSITY_DECLARATION = {
    "name": "get_screen_density",
    "description": "Get the current Android display density in dots per inch.",
    "parameters": {"type": "OBJECT", "properties": {}},
}

GET_MEDIA_VOLUME_DECLARATION = {
    "name": "get_media_volume",
    "description": "Get the current Android media-stream volume as a percentage.",
    "parameters": {"type": "OBJECT", "properties": {}},
}

GET_SYSTEM_SCREEN_REFRESH_RATE_DECLARATION = {
    "name": "get_screen_refresh_rate",
    "description": "Get the current Android display refresh rate in Hz.",
    "parameters": {"type": "OBJECT", "properties": {}},
}

GET_SYSTEM_SCREEN_TIMEOUT_DECLARATION = {
    "name": "get_screen_timeout",
    "description": "Get the Android screen-off timeout duration.",
    "parameters": {"type": "OBJECT", "properties": {}},
}

GET_SYSTEM_BATTERY_STATUS_DECLARATION = {
    "name": "get_system_battery_status",
    "description": "Get the Android device battery level, status, health, temperature, voltage, and power source.",
    "parameters": {"type": "OBJECT", "properties": {}},
}

GET_SYSTEM_CPU_USAGE_DECLARATION = {
    "name": "get_system_cpu_usage",
    "description": "Get the current aggregate system CPU usage percentage.",
    "parameters": {"type": "OBJECT", "properties": {}},
}

GET_SYSTEM_MEMORY_USAGE_DECLARATION = {
    "name": "get_system_memory_usage",
    "description": "Get total, used, and available system memory in bytes.",
    "parameters": {"type": "OBJECT", "properties": {}},
}

GET_SYSTEM_BOOT_TIME_DECLARATION = {
    "name": "get_system_boot_time",
    "description": "Get the device boot time as local ISO-8601 text.",
    "parameters": {"type": "OBJECT", "properties": {}},
}

GET_SYSTEM_SWAP_USAGE_DECLARATION = {
    "name": "get_system_swap_usage",
    "description": "Get total, used, and free system swap in bytes.",
    "parameters": {"type": "OBJECT", "properties": {}},
}

GET_LOAD_AVERAGE_DECLARATION = {
    "name": "get_load_average",
    "description": "Get the 1, 5, and 15 minute system load averages.",
    "parameters": {"type": "OBJECT", "properties": {}},
}
GET_PROCESS_STATUS_DECLARATION = {
    "name": "get_process_status",
    "description": "Get basic status information for a visible local process.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "pid": {"type": "STRING", "description": "Positive process ID to inspect."}
        },
        "required": ["pid"],
    },
}

TOOL_HANDLERS: dict[str, Callable[..., str]] = {
    "discover_android_mechanisms": discover_android_mechanisms,
    "resolve_android_intent": resolve_android_intent,
    "discover_camera_control": discover_camera_control,
    "plan_capability_extension": plan_capability_extension,
    "apply_capability_extension": apply_capability_extension,
    "assess_capability_gap": assess_capability_gap,
    "capability_inventory": capability_inventory,
    "self_test": self_test,
    "find_executable": find_executable,
    "diagnose_command_failure": diagnose_command_failure,
    "verify_command_result": verify_command_result,
    "retry_command": retry_command,
    "recover_command": recover_command,
    "run_command": run_command,
    "run_root_command": run_root_command,
    "list_processes": list_processes,
    "get_process_status": get_process_status,
    "get_process_command_line": get_process_command_line,
    "get_process_executable": get_process_executable,
    "get_process_working_directory": get_process_working_directory,
    "get_process_parent_name": get_process_parent_name,
    "get_process_start_time": get_process_start_time,
    "get_process_cpu_time": get_process_cpu_time,
    "get_process_nice": get_process_nice,
        "get_process_memory_usage": get_process_memory_usage,
    "send_android_keyevent": send_android_keyevent,
    "inspect_android_ui": inspect_android_ui,
    "send_android_intent": send_android_intent,
    "calculator": calculator,
    "current_datetime": current_datetime,
    "get_hostname": get_hostname,
    "get_network_addresses": get_network_addresses,
    "get_wifi_status": get_wifi_status,
    "get_bluetooth_status": get_bluetooth_status,
    "get_airplane_mode": get_airplane_mode,
    "get_load_average": get_load_average,
    "get_system_uptime": get_system_uptime,
    "get_system_boot_time": get_system_boot_time,
    "get_system_swap_usage": get_system_swap_usage,
    "get_screen_brightness_mode": get_screen_brightness_mode,
    "get_screen_orientation": get_screen_orientation,
    "get_screen_resolution": get_screen_resolution,
    "get_screen_density": get_screen_density,
    "get_media_volume": get_media_volume,
    "get_screen_refresh_rate": get_screen_refresh_rate,
    "get_screen_timeout": get_screen_timeout,
    "get_system_battery_status": get_system_battery_status,
    "get_screen_state": get_screen_state,
    "get_screen_brightness": get_screen_brightness,
    "get_system_cpu_usage": get_system_cpu_usage,
    "get_system_memory_usage": get_system_memory_usage,
    "get_network_interfaces": get_network_interfaces,
    "get_system_info": get_system_info,
    "get_process_id": get_process_id,
    "get_current_working_directory": get_current_working_directory,
    "get_python_executable": get_python_executable,
    "get_cpu_count": get_cpu_count,
    "get_memory_usage": get_memory_usage,
    "get_temp_directory": get_temp_directory,
    "get_home_directory": get_home_directory,
    "get_process_uptime": get_process_uptime,
    "get_process_thread_count": get_process_thread_count,
    "get_parent_process_id": get_parent_process_id,
    "get_process_group_id": get_process_group_id,
    "get_session_id": get_session_id,
    "get_user_id": get_user_id,
    "get_umask": get_umask,
    "remember_fact": remember_fact,
    "forget_fact": forget_fact,
    "list_memory": list_memory,
    "path_exists": path_exists,
    "create_directory": create_directory,
    "delete_directory": delete_directory,
    "get_file_info": get_file_info,
    "get_file_access_time": get_file_access_time,
    "get_file_modified_time": get_file_modified_time,
    "get_file_extension": get_file_extension,
    "get_file_name": get_file_name,
    "get_file_stem": get_file_stem,
    "get_file_parent": get_file_parent,
    "get_file_permissions": get_file_permissions,
    "list_directory_recursive": list_directory_recursive,
    "move_directory": move_directory,
    "copy_directory": copy_directory,
    "hash_file": hash_file,
    "get_directory_entry_count": get_directory_entry_count,
    "get_disk_usage": get_disk_usage,
    "get_directory_size": get_directory_size,
    "count_file_lines": count_file_lines,
    "list_directory": list_directory,
    "read_text_file": read_text_file,
    "write_text_file": write_text_file,
    "edit_text_file": edit_text_file,
    "append_text_file": append_text_file,
    "copy_file": copy_file,
    "move_file": move_file,
    "delete_file": delete_file,
    "find_files": find_files,
    "search_text": search_text,
}


GET_SYSTEM_SCREEN_TIMEOUT_DECLARATION = {
    "name": "get_screen_timeout",
    "description": "Get the Android screen-off timeout duration.",
    "parameters": {"type": "OBJECT", "properties": {}},
}

