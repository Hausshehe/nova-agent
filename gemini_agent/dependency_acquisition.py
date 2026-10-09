"""Controlled dependency acquisition through configured Termux repositories.

Only named packages from an explicit development-tool allowlist may be installed.
No arbitrary URLs, shell commands, or user-controlled package-manager flags are accepted.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

_ALLOWED_PACKAGES = {
    "openjdk-17", "openjdk-21", "gradle", "aapt", "aapt2", "ecj", "dx",
    "zip", "unzip", "wget", "curl", "git", "clang", "make", "cmake",
    "ninja", "python", "python-pip", "android-tools", "apksigner",
    "libandroid-support", "binutils", "ndk-sysroot",
}
_PACKAGE_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]{0,63}$")
_MAX_PACKAGES = 12
_MAX_TIMEOUT = 120
_MAX_OUTPUT = 12000


def _trim(value: str) -> str:
    data = value.encode("utf-8", errors="replace")
    if len(data) <= _MAX_OUTPUT:
        return value.rstrip()
    return data[:_MAX_OUTPUT].decode("utf-8", errors="ignore").rstrip() + "\n[output truncated]"


def _package_manager() -> str:
    for name in ("pkg", "apt-get", "apt"):
        path = shutil.which(name)
        # which() already resolves an executable visible in the current process PATH.
        if path:
            return path
    raise RuntimeError("No supported Termux package manager (pkg/apt-get/apt) is available.")


def acquire_termux_packages(packages: list[str], mode: str = "inspect", timeout_seconds: int = 60) -> str:
    """Inspect repository availability or install allowlisted development packages."""
    if not isinstance(packages, list) or not packages or len(packages) > _MAX_PACKAGES:
        raise ValueError(f"packages must contain 1 to {_MAX_PACKAGES} package names.")
    normalized = []
    for package in packages:
        if not isinstance(package, str) or not _PACKAGE_RE.fullmatch(package):
            raise ValueError("Package names must be simple lowercase repository names.")
        if package not in _ALLOWED_PACKAGES:
            raise ValueError(f"Package is not in the dependency-install allowlist: {package}")
        if package not in normalized:
            normalized.append(package)
    if mode not in {"inspect", "install"}:
        raise ValueError("mode must be 'inspect' or 'install'.")
    if not isinstance(timeout_seconds, int) or isinstance(timeout_seconds, bool) or not 1 <= timeout_seconds <= _MAX_TIMEOUT:
        raise ValueError(f"timeout_seconds must be between 1 and {_MAX_TIMEOUT}.")
    manager = _package_manager()
    if mode == "inspect":
        # Read-only repository metadata query. No package scripts are executed.
        command = [manager, "show", *normalized] if Path(manager).name == "pkg" else [manager, "show", *normalized]
    else:
        # Installs are an explicit workspace-goal side effect. The package source is
        # the device's configured repository; callers cannot provide URLs or flags.
        command = [manager, "install", "-y", *normalized] if Path(manager).name == "pkg" else [manager, "install", "-y", *normalized]
    try:
        result = subprocess.run(
            command, cwd=os.getcwd(), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            timeout=timeout_seconds, check=False, shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Package operation timed out after {timeout_seconds} seconds; inspect package state before retrying.") from exc
    except OSError as exc:
        raise RuntimeError(f"Could not start package manager: {exc}") from exc
    stdout, stderr = _trim(result.stdout or ""), _trim(result.stderr or "")
    lines = [
        f"Package operation: {mode.upper()}",
        f"Package manager: {Path(manager).name}",
        f"Packages: {normalized}",
        f"Exit code: {result.returncode}",
    ]
    if stdout:
        lines.append("stdout:\n" + stdout)
    if stderr:
        lines.append("stderr:\n" + stderr)
    if mode == "install" and result.returncode == 0:
        lines.append("Installation command completed; independently verify each required executable/version before relying on it.")
    elif result.returncode != 0:
        lines.append("No success claimed. Diagnose repository, package-name, network, storage, and dependency errors before replanning.")
    return "\n".join(lines)


ACQUIRE_TERMUX_PACKAGES_DECLARATION = {
    "name": "acquire_termux_packages",
    "description": (
        "Inspect configured Termux repository metadata or install allowlisted development dependencies. "
        "Use inspect first to confirm package availability. Installation is limited to approved package names "
        "from configured repositories; no arbitrary URLs, shell commands, or package flags are accepted. "
        "After installation, independently discover and version-check each executable."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "packages": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "One to twelve allowlisted package names."},
            "mode": {"type": "STRING", "enum": ["inspect", "install"], "description": "Inspect package metadata first; use install only when the goal requires the dependency."},
            "timeout_seconds": {"type": "INTEGER", "description": "Bounded operation timeout from 1 to 120 seconds."},
        },
        "required": ["packages", "mode"],
    },
}
