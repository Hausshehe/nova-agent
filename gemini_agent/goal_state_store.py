"""Atomic persistence for Nova's active goal and bounded recovery history."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from gemini_agent.goal_state import GoalState

_STORE_VERSION = 1
_MAX_STORE_BYTES = 64 * 1024


def _default_path() -> Path:
    override = os.environ.get("NOVA_GOAL_STATE_PATH", "").strip()
    return Path(override).expanduser() if override else Path.home() / ".nova-agent" / "active_goal.json"


def save_goal_state(state: GoalState, path: str | os.PathLike[str] | None = None) -> None:
    """Atomically persist a validated goal snapshot; never report success silently."""
    if not isinstance(state, GoalState):
        raise TypeError("Only a GoalState instance can be persisted.")
    target = Path(path).expanduser() if path is not None else _default_path()
    payload = json.dumps(
        {"version": _STORE_VERSION, "goal_state": state.snapshot()},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    encoded = payload.encode("utf-8")
    if len(encoded) > _MAX_STORE_BYTES:
        raise ValueError("Persisted goal state exceeds the storage limit.")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{target.name}.", suffix=".tmp",
            dir=str(target.parent), delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temporary_path, 0o600)
        except OSError:
            pass
        os.replace(temporary_path, target)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except OSError:
                pass


def load_goal_state(path: str | os.PathLike[str] | None = None) -> GoalState | None:
    """Restore a valid active goal; reject corrupt data instead of silently discarding it."""
    target = Path(path).expanduser() if path is not None else _default_path()
    try:
        raw = target.read_bytes()
    except FileNotFoundError:
        return None
    if len(raw) > _MAX_STORE_BYTES:
        raise ValueError("Persisted goal state exceeds the storage limit.")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Persisted goal state is not valid UTF-8 JSON.") from exc
    if not isinstance(document, dict) or document.get("version") != _STORE_VERSION:
        raise ValueError("Persisted goal state has an unsupported format version.")
    data = document.get("goal_state")
    if not isinstance(data, dict):
        raise ValueError("Persisted goal state payload is malformed.")
    try:
        state = GoalState(
            goal=data["goal"],
            success_condition=data["success_condition"],
            status=data["status"],
            progress_status=data["progress_status"],
            progress_reason=data["progress_reason"],
        )
        evidence = data.get("evidence", [])
        steps = data.get("steps", [])
        recovery_history = data.get("recovery_history", [])
        if not isinstance(evidence, list) or len(evidence) > 8:
            raise ValueError("Persisted evidence history is malformed.")
        if not isinstance(steps, list) or len(steps) > 16:
            raise ValueError("Persisted goal step history is malformed.")
        if not isinstance(recovery_history, list) or len(recovery_history) > 8:
            raise ValueError("Persisted recovery history is malformed.")
        for item in evidence:
            state.add_evidence(item)
        for step in steps:
            if not isinstance(step, dict):
                raise ValueError("Persisted goal step is malformed.")
            state.record_step(step["action"], step["status"], step["evidence"])
        for item in recovery_history:
            state.record_recovery(item)
    except (KeyError, TypeError) as exc:
        raise ValueError("Persisted goal state is missing required fields.") from exc
    # Terminal goals remain on disk for audit, but are never resumed as active work.
    return state if state.status == "ACTIVE" else None
