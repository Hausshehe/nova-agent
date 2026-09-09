"""Bounded source-code evidence for Nova self-improvement."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

MAX_FILES = 4
MAX_FILE_CHARS = 8_000
MAX_FILE_LINES = 400
ALLOWED_ROOTS = ("nova_core/", "agent/", "tests/")


@dataclass(frozen=True)
class SourceEvidence:
    """Auditable excerpts from source files relevant to a failed run."""

    revision: str
    files: tuple[tuple[str, str], ...]

    @classmethod
    def from_files(cls, source_root: str | Path, revision: str, paths: tuple[str, ...]) -> "SourceEvidence":
        root = Path(source_root).resolve()
        selected: list[tuple[str, str]] = []
        for raw_path in paths[:MAX_FILES]:
            path = raw_path.replace("\\", "/")
            if not path.startswith(ALLOWED_ROOTS) or ".." in Path(path).parts or path.startswith("/"):
                raise ValueError(f"unsafe source path: {raw_path!r}")
            file_path = (root / path).resolve()
            if root not in file_path.parents:
                raise ValueError(f"source path escapes root: {raw_path!r}")
            if not file_path.is_file():
                raise ValueError(f"source file not found: {raw_path!r}")
            content = file_path.read_text(encoding="utf-8")[:MAX_FILE_CHARS]
            selected.append((path, content))
        return cls(revision=revision, files=tuple(selected))

    def bounded_lines(self) -> tuple[str, ...]:
        lines: list[str] = [f"source.revision={self.revision}"]
        for path, content in self.files:
            lines.append(f"source.file={path}")
            lines.extend(content.splitlines()[:MAX_FILE_LINES])
        return tuple(lines)
