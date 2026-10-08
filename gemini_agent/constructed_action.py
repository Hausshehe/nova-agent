"""Bounded execution of newly constructed local actions."""

import os
import re
import subprocess
from pathlib import Path


_MAX_TIMEOUT_SECONDS = 30
_MAX_OUTPUT_BYTES = 16 * 1024
_ALLOWED_SCOPES = {"WORKSPACE_MUTATION"}
_BLOCKED_EXECUTABLES = {
    "sh", "bash", "dash", "zsh", "fish", "ksh", "csh", "tcsh",
    "python", "python3", "python3.10", "python3.11", "python3.12",
    "python3.13", "python3.14", "perl", "ruby", "node", "nodejs",
    "php", "powershell", "pwsh", "cmd",
}
_SHELL_TOKENS = re.compile(r"[;&|<>\n\r\x00]")


def _filesystem_root() -> Path:
    return Path(os.environ.get("NOVA_FILES_ROOT", os.getcwd())).expanduser().resolve()


def _confined_path(path: str) -> Path:
    if not isinstance(path, str) or not path.strip():
        raise ValueError("Working directory cannot be empty.")
    root = _filesystem_root()
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = root / target
    if target.exists() and target.is_symlink():
        raise ValueError("Working directory cannot be a symlink.")
    target = target.resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("Working directory is outside Nova's allowed filesystem root.") from exc
    if not target.is_dir():
        raise ValueError("Working directory must be an existing directory.")
    return target


def _resolve_executable(executable: str) -> Path:
    if not isinstance(executable, str) or not executable.strip():
        raise ValueError("Executable cannot be empty.")
    candidate = executable.strip()
    if _SHELL_TOKENS.search(candidate):
        raise ValueError("Executable contains shell syntax.")
    name = Path(candidate).name
    if name.lower() in _BLOCKED_EXECUTABLES:
        raise ValueError("Interpreter or shell executables are not permitted for constructed actions.")
    import shutil
    resolved = shutil.which(candidate)
    if resolved is None:
        raise ValueError(f"Executable was not found: {candidate}")
    path = Path(resolved).resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError("Resolved executable is not executable.")
    return path


def _validate_arguments(arguments) -> list[str]:
    if not isinstance(arguments, list):
        raise ValueError("Arguments must be an argv list.")
    if len(arguments) > 64:
        raise ValueError("Too many action arguments.")
    normalized = []
    for argument in arguments:
        if not isinstance(argument, str):
            raise ValueError("Every action argument must be a string.")
        if not argument or "\x00" in argument or "\n" in argument or "\r" in argument:
            raise ValueError("Action arguments cannot contain NUL or newline characters.")
        normalized.append(argument)
    return normalized


def _trim_output(value: str) -> str:
    encoded = value.encode("utf-8", errors="replace")
    if len(encoded) <= _MAX_OUTPUT_BYTES:
        return value.rstrip()
    return encoded[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="ignore").rstrip() + "\n[output truncated]"


def execute_constructed_action(
    executable: str,
    arguments: list[str],
    working_directory: str,
    timeout_seconds: int,
    mutation_scope: str,
    expected_effects: list[str],
    evidence_requirements: list[str],
) -> str:
    """Execute one bounded structured action without shell interpretation."""
    if not isinstance(timeout_seconds, int) or isinstance(timeout_seconds, bool):
        raise ValueError("Timeout must be an integer number of seconds.")
    if timeout_seconds < 1 or timeout_seconds > _MAX_TIMEOUT_SECONDS:
        raise ValueError(f"Timeout must be between 1 and {_MAX_TIMEOUT_SECONDS} seconds.")
    scope = str(mutation_scope).strip().upper()
    if scope not in _ALLOWED_SCOPES:
        raise ValueError("Mutation scope is not currently executable. Allowed scopes: READ_ONLY, WORKSPACE_MUTATION.")
    if not isinstance(expected_effects, list) or any(not isinstance(item, str) or not item.strip() for item in expected_effects):
        raise ValueError("Expected effects must be a list of non-empty strings.")
    if not isinstance(evidence_requirements, list) or any(not isinstance(item, str) or not item.strip() for item in evidence_requirements):
        raise ValueError("Evidence requirements must be a list of non-empty strings.")
    if len(expected_effects) > 32 or len(evidence_requirements) > 32:
        raise ValueError("Too many expected effects or evidence requirements.")

    argv = [_resolve_executable(executable), *_validate_arguments(arguments)]
    cwd = _confined_path(working_directory)

    if any(_SHELL_TOKENS.search(item) for item in argv[1:]):
        raise ValueError("Action arguments contain shell syntax. Use structured argv elements, not shell composition.")

    try:
        completed = subprocess.run(
            [str(item) for item in argv],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Constructed action timed out after {timeout_seconds} seconds.") from exc
    except OSError as exc:
        raise RuntimeError(f"Constructed action failed to start: {exc}") from exc

    stdout = _trim_output(completed.stdout)
    stderr = _trim_output(completed.stderr)
    lines = [
        "Constructed action execution:",
        f"Executable: {argv[0]}",
        f"Arguments: {argv[1:]}",
        f"Working directory: {cwd.relative_to(_filesystem_root()) if cwd != _filesystem_root() else '.'}",
        f"Mutation scope: {scope}",
        f"Exit code: {completed.returncode}",
        f"Expected effects: {expected_effects}",
        f"Evidence requirements: {evidence_requirements}",
    ]
    if stdout:
        lines.append(f"stdout:\n{stdout}")
    if stderr:
        lines.append(f"stderr:\n{stderr}")
    lines.extend([
        "Execution evidence was captured; this tool does not claim that the overall goal was achieved.",
        "Outcome verification must independently establish the requested result.",
    ])
    return "\n".join(lines)


CONSTRUCTED_ACTION_DECLARATION = {
    "name": "execute_constructed_action",
    "description": "Execute one previously unknown workspace-mutating solution action from a bounded structured argv without shell interpretation, while enforcing a confined working directory, execution timeout, mutation scope, and structured execution evidence. This executes an action but does not claim overall goal success.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "executable": {"type": "STRING", "description": "Executable name or path resolvable on the local system."},
            "arguments": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Direct argv elements. Do not provide a shell command string."},
            "working_directory": {"type": "STRING", "description": "Existing directory inside Nova's bounded filesystem root."},
            "timeout_seconds": {"type": "INTEGER", "description": "Execution timeout from 1 to 30 seconds."},
            "mutation_scope": {"type": "STRING", "description": "WORKSPACE_MUTATION is the currently executable scope."},
            "expected_effects": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Declared effects expected from the action."},
            "evidence_requirements": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Evidence that should later be used to verify the result."},
        },
        "required": ["executable", "arguments", "working_directory", "timeout_seconds", "mutation_scope", "expected_effects", "evidence_requirements"],
    },
}
