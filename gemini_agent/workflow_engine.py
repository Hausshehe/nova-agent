"""Bounded composition of existing Nova capabilities; no dynamic code execution."""
from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

MAX_WORKFLOW_STEPS = 8
MAX_ARGUMENT_JSON_CHARS = 12000
MAX_STEP_RESULT_CHARS = 4000
MAX_WORKFLOW_RESULT_CHARS = 16000


def _resolve_references(value: Any, results: list[str]) -> Any:
    """Resolve explicit prior-step references recursively."""
    if isinstance(value, dict):
        if set(value) == {"$step_result"}:
            index = value["$step_result"]
            if not isinstance(index, int) or isinstance(index, bool) or index < 0 or index >= len(results):
                raise ValueError("Workflow reference must point to an earlier completed step.")
            return results[index]
        return {key: _resolve_references(item, results) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_references(item, results) for item in value]
    return value


def validate_workflow(
    steps: list[dict[str, Any]],
    handlers: Mapping[str, Callable[..., Any]],
    *,
    allowed_tools: set[str],
) -> None:
    """Validate a complete workflow before any handler is allowed to run."""
    if not isinstance(steps, list) or not steps:
        raise ValueError("Workflow steps must be a non-empty list.")
    if len(steps) > MAX_WORKFLOW_STEPS:
        raise ValueError(f"Workflow exceeds the {MAX_WORKFLOW_STEPS}-step limit.")

    def check_references(value: Any, step_index: int) -> None:
        if isinstance(value, dict):
            if set(value) == {"$step_result"}:
                index = value["$step_result"]
                if not isinstance(index, int) or isinstance(index, bool) or index < 0 or index >= step_index:
                    raise ValueError("Workflow reference must point to an earlier completed step.")
                return
            for nested in value.values():
                check_references(nested, step_index)
        elif isinstance(value, list):
            for nested in value:
                check_references(nested, step_index)

    for index, step in enumerate(steps):
        if not isinstance(step, dict) or set(step) != {"tool", "arguments"}:
            raise ValueError(f"Step {index} must contain only 'tool' and 'arguments'.")
        name = step["tool"]
        arguments = step["arguments"]
        if not isinstance(name, str) or name not in allowed_tools:
            raise ValueError(f"Step {index} uses a tool not allowed in workflows.")
        if not callable(handlers.get(name)):
            raise ValueError(f"Step {index} references an unavailable registered tool.")
        if not isinstance(arguments, dict):
            raise ValueError(f"Step {index} arguments must be an object.")
        check_references(arguments, index)


def execute_workflow(
    steps: list[dict[str, Any]],
    handlers: Mapping[str, Callable[..., Any]],
    *,
    allowed_tools: set[str],
) -> str:
    """Run a short ordered workflow using explicitly allowed registered handlers."""
    validate_workflow(steps, handlers, allowed_tools=allowed_tools)
    results: list[str] = []
    trace: list[dict[str, Any]] = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict) or set(step) != {"tool", "arguments"}:
            raise ValueError(f"Step {index} must contain only 'tool' and 'arguments'.")
        name = step["tool"]
        arguments = step["arguments"]
        if not isinstance(name, str) or name not in allowed_tools:
            raise ValueError(f"Step {index} uses a tool not allowed in workflows.")
        handler = handlers.get(name)
        if not callable(handler):
            raise ValueError(f"Step {index} references an unavailable registered tool.")
        if not isinstance(arguments, dict):
            raise ValueError(f"Step {index} arguments must be an object.")
        resolved = _resolve_references(arguments, results)
        try:
            result = str(handler(**resolved))
        except Exception as exc:
            trace.append({"step": index, "tool": name, "status": "failed", "error": f"{type(exc).__name__}: {exc}"[:500]})
            break
        result = result[:MAX_STEP_RESULT_CHARS]
        results.append(result)
        trace.append({"step": index, "tool": name, "status": "completed", "result": result})

    status = "completed" if len(trace) == len(steps) and all(item["status"] == "completed" for item in trace) else "failed"
    payload = {"status": status, "steps_completed": len(results), "steps": trace}
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) > MAX_WORKFLOW_RESULT_CHARS:
        payload["steps"] = [
            {key: (value[:1000] if isinstance(value, str) else value) for key, value in item.items()}
            for item in trace
        ]
        payload["truncated"] = True
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))[:MAX_WORKFLOW_RESULT_CHARS]
    return encoded
