"""Bounded repair candidate representation for self-improvement."""

from __future__ import annotations

from dataclasses import dataclass


MAX_PATCH_CHARS = 12_000
MAX_PATHS = 4


@dataclass(frozen=True)
class RepairCandidate:
    """A proposed source change that has not been trusted or adopted."""

    description: str
    patch: str
    paths: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.description.strip():
            raise ValueError("repair candidate requires a description")
        if not self.patch.strip():
            raise ValueError("repair candidate requires a patch")
        if len(self.patch) > MAX_PATCH_CHARS:
            raise ValueError("repair candidate patch exceeds size limit")
        if len(self.paths) > MAX_PATHS:
            raise ValueError("repair candidate touches too many paths")
        for path in self.paths:
            if not path or path.startswith("/") or ".." in path.split("/"):
                raise ValueError(f"unsafe repair path: {path!r}")
            if not path.endswith((".py", ".json", ".toml", ".yaml", ".yml")):
                raise ValueError(f"unsupported repair path: {path!r}")
