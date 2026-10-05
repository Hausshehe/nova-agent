"""Small, safe local tools available to Nova."""

import ast
import datetime as dt
import fnmatch
import hashlib
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
    re.compile(r"^dumpsys\s+[A-Za-z0-9_.-]+(?:\s+[^;&|$]+)?$"),
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
    if parts[0] != executable or executable not in _RUN_COMMAND_ALLOWED:
        raise ValueError(f"Command is not allowed: {executable}")
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
    except RuntimeError as exc:
        first_result = f"Tool error: {exc}"

    if first_result.startswith("Exit code: 0"):
        return "Recovery: none needed.\nAttempts: 1\n" + first_result

    diagnosis = diagnose_command_failure(command, first_result)
    lowered = first_result.lower()

    if "timed out" in lowered:
        retry_result = retry_command(command)
        return diagnosis + "\n" + retry_result

    executable = Path(shlex.split(command)[0]).name
    if any(term in lowered for term in ("not found", "no such file or directory", "command not found")):
        discovered = find_executable(executable)
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

