"""Controlled dependency acquisition through configured Termux repositories.

Read-only inspection accepts syntactically safe package names so Nova can discover
repository contents. Installation is restricted to an explicit development-tool
allowlist. No arbitrary URLs, shell commands, or user-controlled package-manager flags.
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
_METADATA_PACKAGE_RE = re.compile(r"^Package:\s*(\S+)\s*$", re.MULTILINE)
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
    if mode not in {"inspect", "install"}:
        raise ValueError("mode must be 'inspect' or 'install'.")
    if not isinstance(packages, list) or not packages or len(packages) > _MAX_PACKAGES:
        raise ValueError(f"packages must contain 1 to {_MAX_PACKAGES} package names.")
    normalized = []
    for package in packages:
        if not isinstance(package, str) or not _PACKAGE_RE.fullmatch(package):
            raise ValueError("Package names must be simple lowercase repository names.")
        if mode == "install" and package not in _ALLOWED_PACKAGES:
            raise ValueError(f"Package is not in the dependency-install allowlist: {package}")
        if package not in normalized:
            normalized.append(package)
    if not isinstance(timeout_seconds, int) or isinstance(timeout_seconds, bool) or not 1 <= timeout_seconds <= _MAX_TIMEOUT:
        raise ValueError(f"timeout_seconds must be between 1 and {_MAX_TIMEOUT}.")
    manager = _package_manager()
    if mode == "inspect":
        # Read-only repository metadata query. No package scripts are executed.
        command = [manager, "show", *normalized]
    else:
        # Installs are an explicit workspace-goal side effect. The package source is
        # the device's configured repository; callers cannot provide URLs or flags.
        command = [manager, "install", "-y", *normalized]
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
    if mode == "inspect":
        found = set(_METADATA_PACKAGE_RE.findall(stdout))
        lines.append(f"Repository metadata found: {sorted(found)}")
        missing = [package for package in normalized if package not in found]
        if missing:
            lines.append(
                "No metadata returned for: " + ", ".join(missing)
                + ". Availability is unconfirmed; this package manager may omit unknown package names."
            )
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
        "Inspect configured Termux repository metadata for syntactically safe package names, or install allowlisted development dependencies. "
        "Use inspect first to discover package availability. Installation is limited to approved package names "
        "from configured repositories; no arbitrary URLs, shell commands, or package flags are accepted. "
        "After installation, independently discover and version-check each executable."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "packages": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "One to twelve simple lowercase package names; install mode additionally requires allowlisted names."},
            "mode": {"type": "STRING", "enum": ["inspect", "install"], "description": "Inspect package metadata first; use install only when the goal requires the dependency."},
            "timeout_seconds": {"type": "INTEGER", "description": "Bounded operation timeout from 1 to 120 seconds."},
        },
        "required": ["packages", "mode"],
    },
}

def discover_dependency_options(requirements: list[dict]) -> str:
    """Discover executable and repository-package options for generic task requirements."""
    if not isinstance(requirements, list) or not requirements or len(requirements) > 8:
        raise ValueError("requirements must contain 1 to 8 requirement groups.")
    package_names = []
    normalized = []
    for item in requirements:
        if not isinstance(item, dict):
            raise ValueError("Each requirement must be an object.")
        name = item.get("capability")
        executables = item.get("executables", [])
        packages = item.get("packages", [])
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise ValueError("Each requirement needs a non-empty capability label of at most 120 characters.")
        if not isinstance(executables, list) or len(executables) > 8:
            raise ValueError("Each executable candidate list must contain at most 8 names.")
        if not isinstance(packages, list) or len(packages) > 8:
            raise ValueError("Each package candidate list must contain at most 8 names.")
        if not executables and not packages:
            raise ValueError("Each requirement needs executable or package candidates.")
        for executable in executables:
            if not isinstance(executable, str) or not re.fullmatch(r"[A-Za-z0-9_.+-]{1,80}", executable):
                raise ValueError("Executable candidates must be simple command names.")
        for package in packages:
            if not isinstance(package, str) or not _PACKAGE_RE.fullmatch(package):
                raise ValueError("Package candidates must be simple lowercase repository names.")
            if package not in package_names:
                package_names.append(package)
        normalized.append({"capability": name.strip(), "executables": executables, "packages": packages})
    if len(package_names) > _MAX_PACKAGES:
        raise ValueError(f"At most {_MAX_PACKAGES} unique package candidates may be inspected.")
    package_report = acquire_termux_packages(package_names, mode="inspect") if package_names else ""
    found = set(_METADATA_PACKAGE_RE.findall(package_report))
    lines = ["Dependency option discovery (read-only):"]
    for item in normalized:
        lines.append(f"Requirement: {item['capability']}")
        available = []
        unavailable = []
        for executable in item["executables"]:
            path = shutil.which(executable)
            if path:
                available.append(f"{executable}={path}")
            else:
                unavailable.append(executable)
        lines.append("Available executables: " + (", ".join(available) if available else "none found"))
        lines.append("Executables not found: " + (", ".join(unavailable) if unavailable else "none"))
        package_status = [
            f"{package}={'repository metadata found' if package in found else 'availability unconfirmed'}"
            for package in item["packages"]
        ]
        lines.append("Package candidates: " + (", ".join(package_status) if package_status else "none supplied"))
    lines.append("Repository inspection:")
    lines.append(package_report or "No package inspection was needed.")
    lines.append("This is discovery evidence only; no packages were installed and no build strategy was executed.")
    return "\n".join(lines)


DISCOVER_DEPENDENCY_OPTIONS_DECLARATION = {
    "name": "discover_dependency_options",
    "description": (
        "Discover available executables and configured-repository package candidates for generic task requirements. "
        "Supply requirement groups with a capability label, candidate executable names, and candidate package names. "
        "This tool only inspects PATH and repository metadata; it does not install packages or assume one fixed build system."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "requirements": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "capability": {"type": "STRING"},
                        "executables": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "packages": {"type": "ARRAY", "items": {"type": "STRING"}},
                    },
                    "required": ["capability", "executables", "packages"],
                },
                "description": "One to eight task requirements; each may list up to eight executable and package candidates.",
            }
        },
        "required": ["requirements"],
    },
}

