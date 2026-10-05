"""Small, safe local tools available to Nova."""

import ast
import datetime as dt
import fnmatch
import hashlib
import re
import operator
import os
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


def current_datetime() -> str:
    """Return the device's current local date and time."""
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


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

TOOL_HANDLERS: dict[str, Callable[..., str]] = {
    "calculator": calculator,
    "current_datetime": current_datetime,
    "remember_fact": remember_fact,
    "forget_fact": forget_fact,
    "list_memory": list_memory,
    "path_exists": path_exists,
    "create_directory": create_directory,
    "delete_directory": delete_directory,
    "get_file_info": get_file_info,
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
