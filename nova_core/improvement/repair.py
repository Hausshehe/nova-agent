"""Bounded repair candidate representation for self-improvement."""

from __future__ import annotations

import re
from dataclasses import dataclass


MAX_PATCH_CHARS = 12_000
MAX_PATHS = 4
ALLOWED_PATH_PREFIXES = ("nova_core/", "agent/", "tests/")
_DIFF_PATH = re.compile(r"^(?:---|\+\+\+) (?:a/|b/)?(.+)$")


@dataclass(frozen=True)
class RepairCandidate:
    """A proposed source change that has not been trusted or adopted."""

    description: str
    patch: str
    paths: tuple[str, ...] = ()

    @staticmethod
    def _safe_path(path: str) -> bool:
        return (
            bool(path)
            and not path.startswith("/")
            and ".." not in path.split("/")
            and path.startswith(ALLOWED_PATH_PREFIXES)
            and path.endswith(".py")
        )

    def _patch_paths(self) -> tuple[str, ...]:
        found: set[str] = set()
        for line in self.patch.splitlines():
            match = _DIFF_PATH.match(line)
            if match:
                path = match.group(1).strip()
                if path == "/dev/null":
                    continue
                found.add(path)
        return tuple(sorted(found))

    def validate(self) -> None:
        if not self.description.strip():
            raise ValueError("repair candidate requires a description")
        if not self.patch.strip():
            raise ValueError("repair candidate requires a patch")
        if len(self.patch) > MAX_PATCH_CHARS:
            raise ValueError("repair candidate patch exceeds size limit")
        if len(self.paths) > MAX_PATHS:
            raise ValueError("repair candidate touches too many paths")
        declared = tuple(sorted(set(self.paths)))
        if len(declared) != len(self.paths):
            raise ValueError("repair candidate paths must be unique")
        for path in declared:
            if not self._safe_path(path):
                raise ValueError(f"unsafe repair path: {path!r}")
        patch_paths = self._patch_paths()
        if not patch_paths:
            raise ValueError("repair candidate patch contains no source paths")
        if any(not self._safe_path(path) for path in patch_paths):
            raise ValueError("repair candidate patch contains an unsafe path")
        if set(patch_paths) != set(declared):
            raise ValueError("repair candidate paths do not match patch paths")
