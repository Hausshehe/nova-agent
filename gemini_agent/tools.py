"""Small, safe local tools available to Nova."""

import ast
import datetime as dt
import fnmatch
import hashlib
import inspect
import json
import re
import operator
import shlex
import shutil
import subprocess
import time
import shutil
import os
import platform
import socket
import tempfile
import time
import xml.etree.ElementTree as ET
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

def diagnose_capability_failure(capability: str, failure_evidence: str) -> str:
    """Diagnose a local capability failure without executing or modifying the capability."""
    if not isinstance(capability, str) or not capability.strip():
        raise ValueError("Capability cannot be empty.")
    if not isinstance(failure_evidence, str) or not failure_evidence.strip():
        raise ValueError("Failure evidence cannot be empty.")

    name = capability.strip()
    evidence = failure_evidence.strip()
    declaration = next((
        item for item in TOOL_DECLARATIONS
        if isinstance(item, dict) and item.get("name") == name
    ), None)
    handler = TOOL_HANDLERS.get(name)

    lines = ["Capability failure diagnosis (read-only):", f"Capability: {name}", f"Supplied failure evidence: {evidence}"]

    if declaration is None:
        lines.append("Declaration: MISSING")
    else:
        lines.append("Declaration: PRESENT")

    if handler is None:
        lines.append("Handler: MISSING")
    elif not callable(handler):
        lines.append("Handler: INVALID (not callable)")
    else:
        lines.append("Handler: PRESENT and callable")

    if declaration is None or handler is None or not callable(handler):
        lines.extend([
            "Diagnosis: capability registration integrity is broken.",
            "Repairability: bounded registration repair may be possible, but no mutation was performed.",
            "Recovery decision: REPAIR_REQUIRED.",
            "No capability execution, code modification, or device state change was performed.",
        ])
        return "\n".join(lines)

    generated = bool(
        getattr(handler, "__nova_generated_capability__", False)
        or (
            getattr(handler, "__code__", None) is not None
            and any(
                marker in handler.__code__.co_names
                for marker in ("_run_android_mechanism_extension", "_run_extension_primitive")
            )
        )
    )
    lines.append(f"Implementation class: {'GENERATED' if generated else 'LOCAL'}")

    if generated:
        try:
            persisted = _load_persisted_capability_extensions()
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            lines.append(f"Persisted repair metadata: UNAVAILABLE ({exc})")
        else:
            entry = next((
                item for item in persisted
                if isinstance(item, dict) and item.get("name") == name
            ), None)
            if entry is None:
                lines.append("Persisted repair metadata: MISSING")
            else:
                lines.append("Persisted repair metadata: PRESENT")
                target_kind = str(entry.get("implementation_kind", "")).strip().lower()
                target = str(entry.get("implementation_target", "")).strip()
                if target_kind == "android_mechanism" and target:
                    try:
                        validation = validate_android_mechanism(str(entry.get("request", name)), target)
                    except (RuntimeError, ValueError) as exc:
                        lines.append(f"Persisted mechanism validation: UNAVAILABLE ({exc})")
                    else:
                        lines.append("Persisted mechanism validation: " + ("VIABLE" if "Status: VIABLE" in validation else "NOT VIABLE"))
                elif target_kind == "existing_tool" and target:
                    lines.append("Persisted implementation target: " + ("PRESENT" if target in TOOL_HANDLERS else "MISSING"))

    if generated and any("Persisted repair metadata: PRESENT" in line for line in lines):
        lines.extend([
            "Diagnosis: runtime failure is associated with a generated capability that has a persisted repair recipe.",
            "Repairability: RESTORE_GENERATED_CAPABILITY is a bounded candidate; repair must still be tested and real-world verified before persistence is accepted.",
            "Recovery decision: REPAIR_CANDIDATE_AVAILABLE.",
        ])
    else:
        lines.extend([
            "Diagnosis: the supplied evidence establishes a failure report, but it does not identify a safe generic repair mutation.",
            "Repairability: requires additional failure-specific evidence or a bounded repair strategy.",
            "Recovery decision: OBSERVE_AND_ANALYZE.",
        ])

    lines.append("No capability execution, code modification, or device state change was performed.")
    return "\n".join(lines)

def select_capability_repair_candidate(capability: str, diagnosis: str) -> str:
    """Select a bounded repair candidate from read-only capability state."""
    if not isinstance(capability, str) or not capability.strip():
        raise ValueError("Capability cannot be empty.")
    if not isinstance(diagnosis, str) or not diagnosis.strip():
        raise ValueError("Diagnosis cannot be empty.")
    name = capability.strip()
    lines = ["Capability repair-candidate selection (read-only):", f"Capability: {name}", "Selection evidence: supplied diagnosis plus current registration state."]
    declaration = next((item for item in TOOL_DECLARATIONS if isinstance(item, dict) and item.get("name") == name), None)
    handler = TOOL_HANDLERS.get(name)
    if declaration is None or handler is None or not callable(handler):
        lines += ["Candidate: REPAIR_REGISTRATION", "Basis: capability registration is incomplete or invalid.", "Safety boundary: repair only the bounded declaration/handler registration; do not invent implementation code.", "Status: CANDIDATE_SELECTED", "No capability execution or mutation was performed."]
        return "\n".join(lines)
    generated = bool(getattr(handler, "__nova_generated_capability__", False) or (getattr(handler, "__code__", None) is not None and any(marker in handler.__code__.co_names for marker in ("_run_android_mechanism_extension", "_run_extension_primitive"))))
    if not generated:
        lines += ["Candidate: NONE", "Basis: capability is locally implemented and the supplied diagnosis does not establish a bounded generic repair target.", "Safety boundary: do not mutate a local implementation without failure-specific evidence identifying a bounded repair.", "Status: NO_SAFE_CANDIDATE", "No capability execution or mutation was performed."]
        return "\n".join(lines)
    try:
        persisted = _load_persisted_capability_extensions()
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        lines += ["Candidate: NONE", f"Basis: persisted repair metadata is unavailable ({exc}).", "Safety boundary: do not reconstruct generated implementation from inference.", "Status: NO_SAFE_CANDIDATE", "No capability execution or mutation was performed."]
        return "\n".join(lines)
    entry = next((item for item in persisted if isinstance(item, dict) and item.get("name") == name), None)
    if entry is None:
        lines += ["Candidate: NONE", "Basis: no persisted verified repair recipe exists for this generated capability.", "Safety boundary: do not invent a replacement implementation.", "Status: NO_SAFE_CANDIDATE", "No capability execution or mutation was performed."]
        return "\n".join(lines)
    kind = str(entry.get("implementation_kind", "")).strip().lower()
    target = str(entry.get("implementation_target", "")).strip()
    if kind not in {"existing_tool", "android_mechanism"} or not target:
        lines += ["Candidate: NONE", "Basis: persisted recipe is malformed or outside the bounded repair classes.", "Safety boundary: reject unbounded repair metadata.", "Status: NO_SAFE_CANDIDATE", "No capability execution or mutation was performed."]
        return "\n".join(lines)
    if kind == "existing_tool" and target not in TOOL_HANDLERS:
        lines += ["Candidate: NONE", f"Basis: persisted existing-tool target '{target}' is no longer registered.", "Safety boundary: do not substitute an inferred target.", "Status: NO_SAFE_CANDIDATE", "No capability execution or mutation was performed."]
        return "\n".join(lines)
    lines += ["Candidate: RESTORE_GENERATED_CAPABILITY", f"Implementation kind: {kind}", f"Implementation target: {target}", "Basis: generated capability has a persisted bounded repair recipe.", "Safety boundary: restore only from the persisted recipe; deterministic tests and real-world verification are required before acceptance.", "Status: CANDIDATE_SELECTED", "No capability execution or mutation was performed."]
    return "\n".join(lines)
def apply_capability_repair(capability: str, candidate: str) -> str:
    """Apply one bounded self-repair transaction from a persisted verified recipe."""
    if not isinstance(capability, str) or not capability.strip():
        raise ValueError("Capability cannot be empty.")
    if not isinstance(candidate, str) or not candidate.strip():
        raise ValueError("Repair candidate cannot be empty.")
    name = capability.strip()
    selected = candidate.strip()
    if selected != "RESTORE_GENERATED_CAPABILITY":
        return "Capability repair not applied: unsupported repair candidate. Only RESTORE_GENERATED_CAPABILITY is currently bounded."

    store_path = _extension_store_path()
    if not store_path.exists():
        return "Capability repair not applied: persisted repair metadata is unavailable."
    try:
        entries = json.loads(store_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"Capability repair not applied: persisted repair metadata could not be read: {exc}"
    if not isinstance(entries, list):
        return "Capability repair not applied: persisted capability store is not a JSON list."
    entry = next((item for item in entries if isinstance(item, dict) and item.get("name") == name), None)
    if entry is None:
        return f"Capability repair not applied: no persisted verified repair recipe exists for '{name}'."

    kind = str(entry.get("implementation_kind", "")).strip().lower()
    target = str(entry.get("implementation_target", "")).strip()
    arguments = entry.get("implementation_args", "")
    request = str(entry.get("request", "")).strip()
    description = str(entry.get("description", "")).strip()
    if kind not in {"existing_tool", "android_mechanism"} or not target or not isinstance(arguments, str) or not request or not description:
        return "Capability repair not applied: persisted repair recipe is malformed."
    if kind == "existing_tool" and target not in TOOL_HANDLERS:
        return f"Capability repair not applied: persisted existing-tool target '{target}' is no longer registered."
    if kind == "android_mechanism":
        target = _normalize_android_mechanism_target(target)
        if not re.fullmatch(r"(?:intent|ui|ui-text):[^\s,]+", target, re.IGNORECASE):
            return "Capability repair not applied: persisted Android mechanism is outside the bounded repair classes."
        if arguments.strip() not in {"", "{}"}:
            return "Capability repair not applied: persisted Android mechanism arguments are invalid."
        validation = validate_android_mechanism(request, target)
        if "Status: VIABLE" not in validation:
            return "Capability repair not applied: persisted Android mechanism is no longer viable.\n" + validation

    original_handlers = dict(TOOL_HANDLERS)
    original_declarations = list(TOOL_DECLARATIONS)
    try:
        if not _restore_persisted_capability_entry(entry, replace_existing=True):
            raise RuntimeError("persisted recipe could not restore the capability registration")
        repaired = TOOL_HANDLERS.get(name)
        repaired_declaration = next((item for item in TOOL_DECLARATIONS if isinstance(item, dict) and item.get("name") == name), None)
        if repaired is None or not callable(repaired) or repaired_declaration is None:
            raise RuntimeError("persisted recipe did not restore the capability registration")
        passed, verification = _run_extension_test_suite()
        if not passed:
            raise RuntimeError(f"deterministic repair tests failed: {verification}")
    except Exception as exc:
        TOOL_HANDLERS.clear()
        TOOL_HANDLERS.update(original_handlers)
        TOOL_DECLARATIONS[:] = original_declarations
        return f"Capability repair rolled back: {exc}. Original capability registration was restored."

    return (
        f"Capability repair transaction applied: {name}\n"
        f"Repair candidate: {selected}\n"
        f"Implementation kind: {kind}\n"
        f"Implementation target: {target}\n"
        "Snapshot: captured before mutation.\n"
        "Repair action: restored from persisted verified recipe.\n"
        f"{verification}\n"
        "Real-world verification status: PENDING; the repaired capability must be executed and independently verified before this repair is accepted."
    )



def _outcome_ledger_path() -> Path:
    """Return the persistent bounded ledger for capability outcomes."""
    configured = os.environ.get("NOVA_OUTCOME_LEDGER", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".nova-agent-outcomes.json"


def record_capability_outcome(
    capability: str,
    stage: str,
    status: str,
    evidence: str,
) -> str:
    """Append one bounded, structured capability outcome to the persistent ledger."""
    if not isinstance(capability, str) or not capability.strip():
        raise ValueError("Capability cannot be empty.")
    if not isinstance(stage, str) or not stage.strip():
        raise ValueError("Outcome stage cannot be empty.")
    if not isinstance(status, str) or not status.strip():
        raise ValueError("Outcome status cannot be empty.")
    if not isinstance(evidence, str) or not evidence.strip():
        raise ValueError("Outcome evidence cannot be empty.")
    event = {
        "capability": capability.strip(),
        "stage": stage.strip().upper(),
        "status": status.strip().upper(),
        "evidence": evidence.strip()[:_MAX_READ_BYTES],
        "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    path = _outcome_ledger_path()
    entries = []
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return f"Capability outcome not recorded: ledger could not be read: {exc}"
        if not isinstance(loaded, list):
            return "Capability outcome not recorded: ledger is not a JSON list."
        entries = loaded
    entries.append(event)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as temp_file:
            json.dump(entries, temp_file, ensure_ascii=False, indent=2)
            temp_file.write("\n")
            temp_path = Path(temp_file.name)
        os.replace(temp_path, path)
    except (OSError, TypeError, ValueError) as exc:
        try:
            if "temp_path" in locals():
                temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        return f"Capability outcome not recorded: ledger write failed: {exc}"
    return (
        f"Capability outcome recorded: {event['capability']}\n"
        f"Stage: {event['stage']}\n"
        f"Status: {event['status']}\n"
        "Evidence persisted."
    )


def get_capability_outcome_history(capability: str, limit: int = 20) -> str:
    """Read a bounded capability outcome history without modifying it."""
    if not isinstance(capability, str) or not capability.strip():
        raise ValueError("Capability cannot be empty.")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("History limit must be a positive integer.")
    path = _outcome_ledger_path()
    if not path.exists():
        return f"Capability outcome history: {capability.strip()}\nNo persisted outcomes found."
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"Capability outcome history unavailable: {exc}"
    if not isinstance(entries, list):
        return "Capability outcome history unavailable: ledger is not a JSON list."
    name = capability.strip()
    matches = [
        item for item in entries
        if isinstance(item, dict) and item.get("capability") == name
    ][-limit:]
    if not matches:
        return f"Capability outcome history: {name}\nNo persisted outcomes found."
    lines = [f"Capability outcome history: {name}", f"Entries: {len(matches)}"]
    for index, item in enumerate(matches, 1):
        lines.extend([
            f"{index}. Stage: {item.get('stage', '')}",
            f"   Status: {item.get('status', '')}",
            f"   Evidence: {item.get('evidence', '')}",
            f"   Recorded at: {item.get('recorded_at', '')}",
        ])
    return "\n".join(lines)


def analyze_capability_history(capability: str) -> str:
    """Read persisted outcomes and make a bounded repair-verification decision."""
    if not isinstance(capability, str) or not capability.strip():
        raise ValueError("Capability cannot be empty.")
    name = capability.strip()
    path = _outcome_ledger_path()
    if not path.exists():
        return (
            f"Capability history analysis: {name}\n"
            "Latest verification outcome: MISSING\n"
            "Repair decision: REMAIN_PENDING\n"
            "Basis: no persisted outcome ledger is available."
        )
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return (
            f"Capability history analysis: {name}\n"
            "Latest verification outcome: UNAVAILABLE\n"
            f"Repair decision: STOP_SAFELY\nBasis: outcome ledger could not be read: {exc}"
        )
    if not isinstance(entries, list):
        return (
            f"Capability history analysis: {name}\n"
            "Latest verification outcome: UNAVAILABLE\n"
            "Repair decision: STOP_SAFELY\n"
            "Basis: outcome ledger is not a JSON list."
        )
    matches = [
        item for item in entries
        if isinstance(item, dict)
        and item.get("capability") == name
        and str(item.get("stage", "")).upper() == "VERIFICATION"
    ]
    latest = matches[-1] if matches else None
    if latest is None:
        return (
            f"Capability history analysis: {name}\n"
            "Latest verification outcome: MISSING\n"
            "Repair decision: REMAIN_PENDING\n"
            "Basis: no persisted verification outcome exists for this capability."
        )
    status = str(latest.get("status", "")).strip().upper()
    evidence = str(latest.get("evidence", "")).strip()
    if status == "VERIFIED" and re.search(
        r"(?:Post-action verification|Verification)\s*:\s*VERIFIED\b",
        evidence,
        re.IGNORECASE,
    ):
        decision = "ACCEPT_ELIGIBLE"
        basis = "the latest persisted verification outcome is VERIFIED and its evidence explicitly records VERIFIED."
    elif status == "FAILED":
        decision = "REMAIN_PENDING"
        basis = "the latest persisted verification outcome is FAILED."
    elif status == "INCONCLUSIVE":
        decision = "REVERIFY"
        basis = "the latest persisted verification outcome is INCONCLUSIVE, so acceptance cannot be inferred."
    else:
        decision = "REMAIN_PENDING"
        basis = "the latest persisted verification outcome is not sufficient to establish verified execution."
    return (
        f"Capability history analysis: {name}\n"
        f"Latest verification outcome: {status or 'UNKNOWN'}\n"
        f"Evidence: {evidence}\n"
        f"Repair decision: {decision}\n"
        f"Basis: {basis}\n"
        "No capability execution, code modification, repair mutation, or device state change was performed."
    )


def record_capability_repair_verification(capability: str, verification: str) -> str:
    """Persist the latest bounded execution verification while keeping repair PENDING."""
    if not isinstance(capability, str) or not capability.strip():
        raise ValueError("Capability cannot be empty.")
    if not isinstance(verification, str):
        raise ValueError("Verification evidence must be text.")
    name = capability.strip()
    evidence = verification.strip()
    handler = TOOL_HANDLERS.get(name)
    generated = bool(getattr(handler, "__nova_generated_capability__", False) if handler is not None else False)
    if not generated:
        return f"Repair verification not recorded for {name}: capability is not generated."
    store_path = _extension_store_path()
    if not store_path.exists():
        return f"Repair verification not recorded for {name}: persisted repair metadata is unavailable."
    try:
        entries = json.loads(store_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"Repair verification not recorded for {name}: persisted metadata could not be read: {exc}"
    entry = next((item for item in entries if isinstance(item, dict) and item.get("name") == name), None) if isinstance(entries, list) else None
    if entry is None:
        return f"Repair verification not recorded for {name}: persisted repair recipe is missing."
    entry["repair_status"] = "PENDING"
    entry["repair_verification"] = evidence
    entry["repair_verified_at"] = dt.datetime.now(dt.timezone.utc).isoformat()

    verification_status = ""
    if re.search(r"(?:Post-action verification|Verification)\s*:\s*VERIFIED\b", evidence, re.IGNORECASE):
        verification_status = "VERIFIED"
    elif re.search(r"(?:Post-action verification|Verification)\s*:\s*FAILED\b", evidence, re.IGNORECASE):
        verification_status = "FAILED"
    elif re.search(r"(?:Post-action verification|Verification)\s*:\s*INCONCLUSIVE\b", evidence, re.IGNORECASE):
        verification_status = "INCONCLUSIVE"
    if verification_status:
        ledger_result = record_capability_outcome(
            capability=name,
            stage="verification",
            status=verification_status,
            evidence=evidence,
        )
        if not ledger_result.startswith("Capability outcome recorded:"):
            return (
                f"Repair verification not recorded for {name}: outcome ledger update failed. "
                f"{ledger_result}"
            )
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=store_path.parent, prefix=f".{store_path.name}.", suffix=".tmp", delete=False) as temp_file:
            json.dump(entries, temp_file, ensure_ascii=False, indent=2)
            temp_file.write("\n")
            temp_path = Path(temp_file.name)
        os.replace(temp_path, store_path)
    except (OSError, TypeError, ValueError) as exc:
        try:
            if "temp_path" in locals(): temp_path.unlink(missing_ok=True)
        except OSError: pass
        return f"Repair verification not recorded for {name}: metadata write failed: {exc}"
    return f"Repair verification recorded: {name}\nRepair status: PENDING\nLatest verification evidence persisted."
def accept_verified_capability_repair(capability: str, verification: str = "") -> str:
    """Persist acceptance only when the history analyzer says acceptance is eligible."""
    if not isinstance(capability, str) or not capability.strip():
        raise ValueError("Capability cannot be empty.")
    if not isinstance(verification, str):
        raise ValueError("Verification evidence must be a string.")
    name = capability.strip()
    evidence = verification.strip()
    handler = TOOL_HANDLERS.get(name)
    generated = bool(
        handler is not None
        and (
            getattr(handler, "__nova_generated_capability__", False)
            or (
                getattr(handler, "__code__", None) is not None
                and any(
                    marker in handler.__code__.co_names
                    for marker in ("_run_android_mechanism_extension", "_run_extension_primitive")
                )
            )
        )
    )
    if not generated:
        return (
            f"Repair acceptance not recorded for {name}: capability is not a generated "
            "capability."
        )

    analysis = analyze_capability_history(name)
    if "Repair decision: ACCEPT_ELIGIBLE" not in analysis:
        decision_match = re.search(r"Repair decision:\s*([^\n]+)", analysis)
        decision = decision_match.group(1).strip() if decision_match else "UNKNOWN"
        return (
            f"Repair acceptance not recorded for {name}: history analyzer decision is "
            f"{decision}; repair remains PENDING."
        )

    ledger_path = _outcome_ledger_path()
    try:
        ledger_entries = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"Repair acceptance not recorded for {name}: outcome ledger could not be read: {exc}"
    if not isinstance(ledger_entries, list):
        return f"Repair acceptance not recorded for {name}: outcome ledger is invalid; repair remains PENDING."

    verification_entries = [
        item for item in ledger_entries
        if (
            isinstance(item, dict)
            and item.get("capability") == name
            and str(item.get("stage", "")).upper() == "VERIFICATION"
        )
    ]
    latest = verification_entries[-1] if verification_entries else None
    if latest is None:
        return f"Repair acceptance not recorded for {name}: no persisted verification outcome is available; repair remains PENDING."
    persisted_evidence = str(latest.get("evidence", "")).strip()
    if evidence and evidence != persisted_evidence:
        return (
            f"Repair acceptance not recorded for {name}: supplied verification evidence "
            "does not exactly match the most recent persisted verification evidence; repair remains PENDING."
        )
    evidence = persisted_evidence

    store_path = _extension_store_path()
    if not store_path.exists():
        return f"Repair acceptance not recorded for {name}: persisted repair metadata is unavailable."
    try:
        entries = json.loads(store_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"Repair acceptance not recorded for {name}: persisted metadata could not be read, {exc}"
    if not isinstance(entries, list):
        return f"Repair acceptance not recorded for {name}: persisted capability store is invalid."

    entry = next(
        (item for item in entries if isinstance(item, dict) and item.get("name") == name),
        None,
    )
    if entry is None:
        return f"Repair acceptance not recorded for {name}: persisted repair recipe is missing."

    entry["repair_status"] = "ACCEPTED"
    entry["repair_verification"] = evidence
    entry["repair_verified_at"] = dt.datetime.now(dt.timezone.utc).isoformat()

    try:
        store_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=store_path.parent,
            prefix=f".{store_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            json.dump(entries, temp_file, ensure_ascii=False, indent=2)
            temp_file.write("\n")
            temp_path = Path(temp_file.name)
        os.replace(temp_path, store_path)
    except (OSError, TypeError, ValueError) as exc:
        try:
            if "temp_path" in locals():
                temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        return f"Repair acceptance not recorded for {name}: metadata write failed: {exc}"

    return (
        f"Repair acceptance recorded: {name}\n"
        "Repair status: ACCEPTED\n"
        "Acceptance basis: persisted history analyzer returned ACCEPT_ELIGIBLE.\n"
        "Persisted repair recipe retained."
    )

def capability_inventory() -> str:
    """List the capabilities Nova currently exposes to its local tool runtime."""
    entries = []
    for declaration in TOOL_DECLARATIONS:
        name = declaration.get("name")
        description = declaration.get("description", "")
        if name in TOOL_HANDLERS:
            entries.append(f"- {name}: {description}")
    return f"Capabilities ({len(entries)}):\n" + "\n".join(entries)




def send_android_keyevent(keycode: str) -> str:
    """Send one bounded Android key event through the manually entered root shell."""
    if not isinstance(keycode, str) or not keycode.strip():
        raise ValueError("Keycode cannot be empty.")
    allowed = {"3", "4", "25", "27"}
    normalized = keycode.strip().upper().replace("KEYCODE_", "")
    aliases = {"HOME": "3", "BACK": "4", "VOLUME_DOWN": "25", "CAMERA": "27"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in allowed:
        raise ValueError("Unsupported Android keycode. Allowed actions: HOME, BACK, VOLUME_DOWN, CAMERA.")
    result = _run_bounded_root_action(f"input keyevent {normalized}")
    return f"Android key event {normalized} sent.\n{result}"

def resolve_android_intent(action: str) -> str:
    """Resolve one allowlisted Android intent without launching it."""
    if not isinstance(action, str) or not action.strip():
        raise ValueError("Intent action cannot be empty.")
    normalized = action.strip()
    aliases = {
        "IMAGE_CAPTURE": "android.media.action.IMAGE_CAPTURE",
        "STILL_IMAGE_CAMERA": "android.media.action.STILL_IMAGE_CAMERA",
    }
    normalized = aliases.get(normalized, normalized)
    allowed_actions = {
        "android.media.action.IMAGE_CAPTURE",
        "android.media.action.STILL_IMAGE_CAMERA",
    }
    if normalized not in allowed_actions:
        raise ValueError("Unsupported Android intent action.")
    result = run_root_command(
        f"cmd package resolve-activity --brief -a {normalized}"
    )
    return (
        f"Android intent resolution (read-only): {normalized}\n"
        f"{result}\n"
        "Intent was resolved only; it was not launched and no device state was modified."
    )


def send_android_intent(action: str) -> str:
    """Launch one explicitly allowlisted Android intent action."""
    if not isinstance(action, str) or not action.strip():
        raise ValueError("Intent action cannot be empty.")
    normalized = action.strip()
    aliases = {"IMAGE_CAPTURE": "android.media.action.IMAGE_CAPTURE"}
    normalized = aliases.get(normalized, normalized)
    allowed_actions = {"android.media.action.IMAGE_CAPTURE"}
    if normalized not in allowed_actions:
        raise ValueError("Unsupported Android intent action.")
    result = _run_bounded_root_action(f"am start -a {normalized}")
    return f"Android intent {normalized} started.\n{result}"


def discover_camera_control() -> str:
    """Discover camera-related Android mechanisms without launching or controlling the camera."""
    return discover_android_mechanisms("control the phone camera")

def get_foreground_android_component() -> str:
    """Inspect the current foreground Android package and activity without interacting with it."""
    result = run_root_command("dumpsys activity activities")
    lines = []
    for line in result.splitlines():
        stripped = line.strip()
        if (
            "topResumedActivity=" in stripped
            or "mResumedActivity:" in stripped
            or "ResumedActivity:" in stripped
        ):
            lines.append(stripped)
    if not lines:
        for line in result.splitlines():
            stripped = line.strip()
            if "mActivityComponent=" in stripped or "packageName=" in stripped:
                lines.append(stripped)
                if len(lines) >= 2:
                    break
    if not lines:
        return (
            "Foreground Android component inspection (read-only):\n"
            "No foreground component could be identified from the activity manager output.\n"
            "No interaction or device state change was performed."
        )
    return (
        "Foreground Android component inspection (read-only):\n"
        + "\n".join(lines[:3])
        + "\nNo interaction or device state change was performed."
    )

def verify_android_component_presence(component: str) -> str:
    """Verify an Android component using multiple read-only activity/window evidence sources."""
    if not isinstance(component, str) or not component.strip():
        raise ValueError("Android component cannot be empty.")
    expected = component.strip()
    sources = (
        ("activity", "dumpsys activity activities"),
        ("window", "dumpsys window windows"),
        ("recents", "dumpsys activity recents"),
    )
    evidence = []
    for source_name, command in sources:
        result = run_root_command(command)
        for line in result.splitlines():
            stripped = line.strip()
            if expected not in stripped:
                continue
            if (
                "ActivityRecord" in stripped
                or "mResumedActivity" in stripped
                or "topResumedActivity" in stripped
                or "Window" in stripped
                or "mCurrentFocus" in stripped
                or "mFocusedApp" in stripped
            ):
                evidence.append(f"[{source_name}] {stripped}")
    if evidence:
        return (
            "Android component presence verification (read-only): VERIFIED\\n"
            f"Expected component: {expected}\\n"
            "Evidence:\\n"
            + "\\n".join(evidence[:10])
        )
    return (
        "Android component presence verification (read-only): INCONCLUSIVE\\n"
        f"Expected component: {expected}\\n"
        "No matching evidence was found in the bounded activity, window, or recents observations.\\n"
        "This does not prove the component is absent, so no recovery/replanning should be triggered from this observation alone.\\n"
        "No interaction or device state change was performed."
    )


def inspect_android_ui(selector: str = "") -> str:
    """Inspect the current foreground Android UI hierarchy, optionally filtering to one UI selector."""
    if not isinstance(selector, str):
        raise ValueError("Selector must be a string.")

    normalized = selector.strip()
    kind = value = ""
    if normalized:
        if ":" not in normalized:
            raise ValueError("Selector must use ui:<resource-id> or ui-text:<text>.")
        kind, value = normalized.split(":", 1)
        kind = kind.strip().lower()
        value = value.strip()
        if kind not in {"ui", "ui-text"} or not value:
            raise ValueError("Selector must use ui:<resource-id> or ui-text:<text>.")

    dump_path = "/data/local/tmp/nova-ui-hierarchy.xml"
    try:
        dump_result = run_root_command(f"uiautomator dump {dump_path}")
        if not dump_result.startswith("Exit code: 0"):
            return (
                "Android UI inspection (read-only):\n"
                f"{dump_result}\n"
                "UI was inspected only; no interaction or device state change was performed."
            )

        try:
            xml_text = _read_bounded_root_file(dump_path, 64 * 1024)
            root = ET.fromstring(xml_text)
        except (RuntimeError, ValueError, ET.ParseError) as exc:
            return (
                "Android UI inspection (read-only):\n"
                f"UI hierarchy could not be read or parsed: {exc}\n"
                "No interaction or device state change was performed."
            )

        if not normalized:
            return (
                "Android UI inspection (read-only):\n"
                f"{xml_text}\n"
                "UI hierarchy was captured without interaction or device state change."
            )

        attribute = "resource-id" if kind == "ui" else "text"
        matches = [
            node for node in root.iter("node")
            if node.attrib.get(attribute, "") == value
            and node.attrib.get("enabled") == "true"
        ]

        if not matches:
            return (
                "Android UI inspection (read-only):\n"
                f"No enabled UI node matched selector {normalized!r}.\n"
                "No interaction or device state change was performed."
            )
        if len(matches) > 1:
            return (
                "Android UI inspection (read-only):\n"
                f"Selector {normalized!r} matched {len(matches)} enabled UI nodes; inspection is ambiguous.\n"
                "No interaction or device state change was performed."
            )

        attributes = " ".join(
            f"{key}={value!r}" for key, value in matches[0].attrib.items()
        )
        return (
            "Android UI inspection (read-only):\n"
            f"Matched selector: {normalized}\n"
            f"Node attributes: {attributes}\n"
            "No interaction or device state change was performed."
        )
    finally:
        try:
            run_root_command(f"rm -f {dump_path}")
        except (RuntimeError, ValueError):
            pass

def discover_android_ui_actions() -> str:
    """Discover enabled clickable Android UI controls without interacting with the device."""
    dump_path = "/data/local/tmp/nova-ui-actions.xml"
    try:
        dump_result = run_root_command(f"uiautomator dump {dump_path}")
        if not dump_result.startswith("Exit code: 0"):
            return (
                "Android UI action discovery (read-only):\n"
                f"{dump_result}\n"
                "No UI interaction or device state change was performed."
            )
        xml_text = _read_bounded_root_file(dump_path, 64 * 1024)
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            return (
                "Android UI action discovery (read-only):\n"
                f"UI hierarchy could not be parsed: {exc}\n"
                "No UI interaction or device state change was performed."
            )
        controls = []
        candidates = []
        for node in root.iter("node"):
            if node.attrib.get("enabled") != "true":
                continue
            control = {
                "text": node.attrib.get("text", ""),
                "content_desc": node.attrib.get("content-desc", ""),
                "resource_id": node.attrib.get("resource-id", ""),
                "class": node.attrib.get("class", ""),
                "bounds": node.attrib.get("bounds", ""),
                "clickable": node.attrib.get("clickable", ""),
            }
            if control["clickable"] == "true":
                controls.append(control)
            if control["resource_id"] and control["bounds"]:
                candidates.append(control)
        lines = [f"Clickable enabled controls found: {len(controls)}"]
        for index, control in enumerate(controls[:50], 1):
            label = control["text"] or control["content_desc"] or control["resource_id"] or "<unlabeled>"
            lines.append(
                f"{index}. label={label!r} resource_id={control['resource_id']!r} "
                f"class={control['class']!r} bounds={control['bounds']!r}"
            )
        lines.append(f"Enabled UI nodes with resource IDs and bounds: {len(candidates)}")
        for index, candidate in enumerate(candidates[:50], 1):
            label = candidate["text"] or candidate["content_desc"] or candidate["resource_id"] or "<unlabeled>"
            lines.append(
                f"candidate {index}. label={label!r} resource_id={candidate['resource_id']!r} "
                f"clickable={candidate['clickable']!r} class={candidate['class']!r} bounds={candidate['bounds']!r}"
            )
        lines.append("Discovered bounded UI mechanisms:")
        for control in controls[:50]:
            if control["resource_id"]:
                lines.append(f"ui:{control['resource_id']}")
            if control["text"]:
                lines.append(f"ui-text:{control['text']}")
        lines.append("UI actions were discovered only; no interaction or device state change was performed.")
        return "Android UI action discovery (read-only):\n" + "\n".join(lines)
    finally:
        try:
            run_root_command(f"rm -f {dump_path}")
        except (RuntimeError, ValueError):
            pass

_DISCOVERABLE_ANDROID_INTENTS = (
    "android.media.action.IMAGE_CAPTURE",
    "android.media.action.STILL_IMAGE_CAMERA",
)


def discover_android_mechanisms(request: str) -> str:
    """Discover safe, read-only Android mechanisms that may implement a missing capability."""
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Request cannot be empty.")

    requested = request.strip()
    words = [
        word for word in re.findall(r"[a-z0-9_]+", requested.lower())
        if len(word) >= 4
        and word not in {
            "control", "phone", "device", "android", "using", "with",
            "from", "that", "this", "have", "need", "capability",
        }
    ]

    results = [f"Requested capability: {requested}"]
    for executable in ("am", "cmd", "dumpsys", "pm", "uiautomator"):
        results.append(f"{executable}: {find_executable(executable)}")

    # Validate the bounded Android intent catalog against the current device.
    # This is discovery only: no intent is launched.
    intent_candidates = []
    for action in _DISCOVERABLE_ANDROID_INTENTS:
        try:
            evidence = resolve_android_intent(action)
        except (RuntimeError, ValueError) as exc:
            evidence = str(exc)
        if "Intent was resolved only" in evidence:
            intent_candidates.append(f"intent:{action}")
    if intent_candidates:
        results.append("Discovered bounded intent mechanisms:\n" + "\n".join(intent_candidates))

    try:
        ui_discovery = discover_android_ui_actions()
    except (RuntimeError, ValueError) as exc:
        results.append(f"Android UI mechanism discovery unavailable: {exc}")
    else:
        ui_mechanisms = []
        in_section = False
        for line in ui_discovery.splitlines():
            stripped = line.strip()
            if stripped == "Discovered bounded UI mechanisms:":
                in_section = True
                continue
            if in_section and re.fullmatch(r"(?:ui|ui-text):.+", stripped):
                ui_mechanisms.append(stripped)
            elif in_section and stripped.startswith("UI actions were discovered only"):
                break
        if ui_mechanisms:
            results.append("Discovered bounded UI mechanisms:\n" + "\n".join(ui_mechanisms[:50]))
        else:
            results.append("Discovered bounded UI mechanisms: none.")

    try:
        services = run_root_command("dumpsys -l")
    except (RuntimeError, ValueError) as exc:
        results.append(f"Android service discovery unavailable: {exc}")
    else:
        lines = services.splitlines()
        candidates = [
            line.strip()
            for line in lines
            if line.strip() and any(word in line.lower() for word in words)
        ]
        if candidates:
            results.append("Candidate Android services:\n" + "\n".join(candidates[:20]))
        else:
            results.append(
                "Candidate Android services: none matched the request terms. "
                "The capability may require an intent, UI, executable, or another IPC mechanism."
            )

    return (
        "Android mechanism discovery (read-only):\n"
        + "\n".join(results)
        + "\nNo action was performed and no device state was modified."
    )


def validate_android_mechanism(request: str, mechanism: str) -> str:
    """Validate one discovered Android mechanism without executing the requested capability."""
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Request cannot be empty.")
    if not isinstance(mechanism, str) or not mechanism.strip():
        raise ValueError("Mechanism cannot be empty.")

    requested = request.strip()
    candidate = mechanism.strip()
    if ":" not in candidate:
        raise ValueError(
            "Mechanism must use a bounded form: intent:<action>, executable:<name>, "
            "service:<name>, ui:<resource-id>, or ui-text:<text>."
        )

    kind, value = candidate.split(":", 1)
    kind = kind.strip().lower()
    value = value.strip()
    if not value:
        raise ValueError("Mechanism value cannot be empty.")

    evidence = ""
    if kind == "intent":
        evidence = resolve_android_intent(value)
    elif kind == "executable":
        evidence = find_executable(value)
    elif kind == "service":
        services = run_root_command("dumpsys -l")
        matches = [line.strip() for line in services.splitlines() if line.strip() == value]
        evidence = "\n".join(matches) if matches else "Service was not found."
    elif kind in {"ui", "ui-text"}:
        dump_path = "/data/local/tmp/nova-ui-validation.xml"
        try:
            dump_result = run_root_command(f"uiautomator dump {dump_path}")
            if not dump_result.startswith("Exit code: 0"):
                evidence = f"UI hierarchy could not be captured.\n{dump_result}"
            else:
                xml_text = _read_bounded_root_file(dump_path, 64 * 1024)
                try:
                    root = ET.fromstring(xml_text)
                except ET.ParseError as exc:
                    evidence = f"UI hierarchy could not be parsed: {exc}"
                else:
                    selector_name = "resource ID" if kind == "ui" else "text"
                    matches = []
                    for node in root.iter("node"):
                        selector_value = (
                            node.attrib.get("resource-id", "")
                            if kind == "ui"
                            else node.attrib.get("text", "")
                        )
                        if (
                            selector_value == value
                            and node.attrib.get("enabled") == "true"
                            and node.attrib.get("bounds")
                        ):
                            matches.append(node)
                    evidence = (
                        f"UI node with the requested {selector_name} was found and has usable bounds."
                        if matches
                        else f"UI node with the requested {selector_name} was not found in the current hierarchy."
                    )
        finally:
            try:
                run_root_command(f"rm -f {dump_path}")
            except (RuntimeError, ValueError):
                pass
    else:
        raise ValueError(
            "Unsupported mechanism type. Allowed types: intent, executable, service, ui, ui-text."
        )

    viable = "not found" not in evidence.lower() and "unsupported" not in evidence.lower()
    status = "VIABLE" if viable else "NOT VIABLE"
    return (
        "Android mechanism validation (read-only):\n"
        f"Requested capability: {requested}\n"
        f"Mechanism: {candidate}\n"
        f"Status: {status}\n"
        f"Evidence:\n{evidence}\n"
        "No capability action was executed and no device state was modified."
    )

def execute_validated_android_ui_mechanism(request: str, mechanism: str) -> str:
    """Lazily dispatch UI execution to avoid the android_ui/tools import cycle."""
    from gemini_agent.android_ui import execute_validated_android_ui_mechanism as _execute_ui
    return _execute_ui(request=request, mechanism=mechanism)


def diagnose_android_mechanism_outcome(
    request: str,
    mechanism: str,
    verification: str,
) -> str:
    """Diagnose Android mechanism evidence without another state-changing action."""
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Request cannot be empty.")
    if not isinstance(mechanism, str) or not mechanism.strip():
        raise ValueError("Mechanism cannot be empty.")
    if not isinstance(verification, str) or not verification.strip():
        raise ValueError("Verification result cannot be empty.")

    candidate = mechanism.strip()
    observed = verification.strip()
    if "VERIFIED" in observed and "INCONCLUSIVE" not in observed and "FAILED" not in observed:
        return (
            "Android mechanism outcome diagnosis (read-only): VERIFIED\n"
            "Evidence is sufficient for the reported postcondition.\n"
            "Recovery decision: NONE.\n"
            "No interaction or device state change was performed."
        )

    evidence = []
    kind = candidate.split(":", 1)[0].lower() if ":" in candidate else ""
    if kind in {"ui", "ui-text"}:
        try:
            observation = inspect_android_ui(candidate)
            if "No enabled UI node matched" in observation:
                evidence.append("Current matching enabled UI nodes: 0")
            elif "matched" in observation.lower():
                evidence.append("Current UI observation: " + observation.split("Android UI inspection (read-only):", 1)[-1].strip())
            else:
                evidence.append("Current UI observation: " + observation)
        except (RuntimeError, ValueError) as exc:
            evidence.append(f"Current UI observation unavailable: {exc}")
    elif kind == "intent":
        try:
            foreground = get_foreground_android_component()
            evidence.append(foreground.replace(
                "No interaction or device state change was performed.", ""
            ).strip())
        except (RuntimeError, ValueError) as exc:
            evidence.append(f"Foreground observation unavailable: {exc}")

    return (
        "Android mechanism outcome diagnosis (read-only): INCONCLUSIVE\n"
        f"Requested capability: {request.strip()}\n"
        f"Mechanism: {candidate}\n"
        f"Reported verification: {observed}\n"
        "Diagnosis: the bounded evidence does not prove whether the requested goal was achieved.\n"
        + ("Evidence:\n" + "\n".join(evidence) + "\n" if evidence else "")
        + "Recovery decision: OBSERVE_OR_REPLAN, but do not perform another state-changing action from uncertainty alone.\n"
        "No interaction or device state change was performed by diagnosis."
    )


def recover_android_mechanism(
    request: str,
    mechanism: str,
    verification: str,
) -> str:
    """Diagnose an Android outcome and replan only when bounded evidence justifies it."""
    diagnosis = diagnose_android_mechanism_outcome(
        request=request,
        mechanism=mechanism,
        verification=verification,
    )
    if "Recovery decision: NONE." in diagnosis:
        return diagnosis + "\nRecovery action: NONE."
    if "Recovery decision: OBSERVE_OR_REPLAN" not in diagnosis:
        return diagnosis + "\nRecovery action: STOP_SAFELY."
    # Uncertainty alone is not permission to perform another state-changing action.
    if "INCONCLUSIVE" in verification.upper():
        return (
            diagnosis
            + "\nRecovery action: NONE. The outcome is uncertain, so no alternate "
              "mechanism was executed from uncertainty alone."
        )
    if "FAILED" in verification.upper():
        recovery = replan_android_mechanism(request, mechanism)
        return diagnosis + "\nRecovery action:\n" + recovery
    return diagnosis + "\nRecovery action: NONE."

def rank_android_mechanism_candidates(
    request: str, candidates: list[str]
) -> list[str]:
    """Prefer mechanism types explicitly required by the goal."""
    text = str(request).lower()
    preferred_kinds = []
    if any(term in text for term in (
        "ui", "user interface", "visible", "clickable", "control", "button"
    )):
        preferred_kinds.extend(["ui-text", "ui"])
    if any(term in text for term in ("intent", "activity", "launch")):
        preferred_kinds.append("intent")
    if any(term in text for term in ("executable", "command", "binary")):
        preferred_kinds.append("executable")
    if any(term in text for term in ("service", "daemon")):
        preferred_kinds.append("service")
    if not preferred_kinds:
        return candidates
    rank = {kind: index for index, kind in enumerate(preferred_kinds)}
    return [
        candidate
        for _, candidate in sorted(
            enumerate(candidates),
            key=lambda item: (
                rank.get(item[1].split(":", 1)[0].lower(), len(rank)),
                item[0],
            ),
        )
    ]


def replan_android_mechanism(request: str, failed_mechanism: str) -> str:
    """Discover, validate, and execute one untried Android mechanism through the generic dispatcher."""
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Request cannot be empty.")
    if not isinstance(failed_mechanism, str) or not failed_mechanism.strip():
        raise ValueError("Failed mechanism cannot be empty.")

    try:
        discovered = discover_android_mechanisms(request)
        alternatives = re.findall(
            r"(?m)^(intent|ui-text|ui):(.+)$", discovered
        )
        alternatives = rank_android_mechanism_candidates(
            request,
            [f"{kind}:{value}" for kind, value in alternatives],
        )
    except (RuntimeError, ValueError) as exc:
        return f"Replan: mechanism discovery failed: {exc}"

    for alternative_mechanism in alternatives:
        if alternative_mechanism.lower() == failed_mechanism.strip().lower():
            continue
        try:
            validation = validate_android_mechanism(request, alternative_mechanism)
        except (RuntimeError, ValueError):
            continue
        if "Status: VIABLE" not in validation:
            continue
        result = execute_android_mechanism(
            request=request,
            mechanism=alternative_mechanism,
            allow_recovery=False,
        )
        if "Post-action verification: VERIFIED" in result:
            return (
                "Replan: selected alternate viable mechanism.\n"
                f"Mechanism: {alternative_mechanism}\n"
                f"{result}"
            )
        if "Post-action verification: INCONCLUSIVE" in result:
            return (
                "Replan: selected alternate viable mechanism, but its outcome is INCONCLUSIVE.\n"
                f"Mechanism: {alternative_mechanism}\n"
                f"{result}"
            )
        if "Post-action verification: FAILED" in result:
            return (
                "Replan: selected alternate viable mechanism, but its postcondition FAILED.\n"
                f"Mechanism: {alternative_mechanism}\n"
                f"{result}"
            )
        return (
            "Replan: selected alternate viable mechanism, but its outcome is UNVERIFIED.\n"
            f"Mechanism: {alternative_mechanism}\n"
            f"{result}"
        )

    return "Replan: no untried viable alternative Android mechanism was found.\nOutcome: FAILED"

def execute_android_mechanism(
    request: str,
    mechanism: str,
    allow_recovery: bool = True,
) -> str:
    """Dispatch one Android mechanism to its bounded executor."""
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Request cannot be empty.")
    if not isinstance(mechanism, str) or not mechanism.strip():
        raise ValueError("Mechanism cannot be empty.")
    candidate = mechanism.strip()
    if ":" not in candidate:
        raise ValueError(
            "Mechanism must use a bounded form: intent:<action>, executable:<name>, "
            "service:<name>, ui:<resource-id>, or ui-text:<text>."
        )
    kind = candidate.split(":", 1)[0].strip().lower()
    if kind == "intent":
        return execute_validated_android_mechanism(request=request, mechanism=candidate, allow_recovery=allow_recovery)
    if kind in {"ui", "ui-text"}:
        from gemini_agent.android_ui import execute_validated_android_ui_mechanism
        return execute_validated_android_ui_mechanism(
            request=request,
            mechanism=candidate,
        )
    return (
        "Android mechanism execution blocked: no bounded executor exists for "
        f"mechanism type '{kind}'."
    )

def execute_validated_android_mechanism(
    request: str,
    mechanism: str,
    allow_recovery: bool = True,
) -> str:
    """Execute one validated Android mechanism, optionally allowing generic recovery."""
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Request cannot be empty.")
    if not isinstance(mechanism, str) or not mechanism.strip():
        raise ValueError("Mechanism cannot be empty.")
    candidate = mechanism.strip()
    if ":" not in candidate:
        raise ValueError("Mechanism must use a bounded form: intent:<action>.")
    kind, value = candidate.split(":", 1)
    kind = kind.strip().lower()
    value = value.strip()
    if kind != "intent":
        raise ValueError(
            "This execution layer currently supports only validated intent mechanisms. "
            "Other mechanism types must remain blocked until they have a bounded action primitive."
        )
    validation = validate_android_mechanism(request, candidate)
    if "Status: VIABLE" not in validation:
        return (
            "Android mechanism execution blocked: the mechanism did not validate as viable.\\n"
            + validation
        )
    result = send_android_intent(value)
    expected_matches = re.findall(
        r"(?<![A-Za-z0-9._$-])([A-Za-z0-9._$-]+/[A-Za-z0-9._$-]+)(?![A-Za-z0-9._$-])",
        validation,
    )
    expected_component = expected_matches[-1] if expected_matches else ""
    verification = "UNVERIFIED: no expected foreground component could be derived from mechanism validation."
    recovery = ""
    if expected_component:
        time.sleep(1)
        foreground = get_foreground_android_component()
        if expected_component in foreground:
            verification = (
                "VERIFIED: expected Android component is foreground: "
                + expected_component
            )
        else:
            presence = verify_android_component_presence(expected_component)
            if "VERIFIED" in presence:
                verification = (
                    "VERIFIED: expected Android component is present in the active "
                    "activity state, but a higher-priority overlay is foreground.\\n"
                    + presence
                )
            elif "INCONCLUSIVE" in presence:
                verification = (
                    "INCONCLUSIVE: intent launch returned successfully, but the expected "
                    "Android component could not be confirmed from the bounded observations. "
                    "The observation is insufficient to declare failure or trigger recovery. "
                    f"Expected: {expected_component}. Observed:\\n{foreground}\\n{presence}"
                )
            else:
                verification = (
                    "FAILED: intent launch returned successfully, but the expected "
                    "Android component was neither foreground nor present in the observed "
                    "activity/window state. "
                    f"Expected: {expected_component}. Observed:\\n{foreground}\\n{presence}"
                )
                # Strong negative evidence is required before mechanism replanning.
                if allow_recovery:
                    recovery = replan_android_mechanism(request, candidate)
    if recovery.startswith("Replan: selected alternate viable mechanism."):
        recovery = "Recovery: discovered an alternate viable Android intent.\n" + recovery
    elif recovery.startswith("Replan: selected alternate viable mechanism,"):
        recovery = "Recovery: discovered an alternate viable Android intent, but its postcondition failed.\n" + recovery
    return (
        "Android mechanism execution:\n"
        f"Requested capability: {request.strip()}\n"
        f"Mechanism: {candidate}\n"
        "Validation: VIABLE\n"
        f"Result:\n{result}\n"
        f"Post-action verification: {verification}"
        + (f"\n{recovery}" if recovery else "")
    )

def assess_capability_gap(request: str) -> str:
    """Determine whether Nova has a plausible local capability for a request."""
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Request cannot be empty.")

    text = request.lower()
    capability_phrases = {
        "camera control": {"camera control": ["discover_camera_control"]},
        "camera shutter mechanism": {"camera shutter mechanism": ["discover_camera_control"]},
        "battery": {"battery": ["get_system_battery_status"]},
        "date and time": {"date and time": ["current_datetime"]},
        "current time": {"current time": ["current_datetime"]},
        "wifi": {"wifi": ["get_wifi_status"]},
        "wi-fi": {"wi-fi": ["get_wifi_status"]},
        "bluetooth": {"bluetooth": ["get_bluetooth_status"]},
        "airplane mode": {"airplane mode": ["get_airplane_mode"]},
        "screen brightness": {"screen brightness": ["get_screen_brightness"]},
        "screen orientation": {"screen orientation": ["get_screen_orientation"]},
        "screen resolution": {"screen resolution": ["get_screen_resolution"]},
        "screen refresh rate": {"screen refresh rate": ["get_screen_refresh_rate"]},
        "screen timeout": {"screen timeout": ["get_screen_timeout"]},
        "memory usage": {"memory usage": ["get_system_memory_usage"]},
        "cpu usage": {"cpu usage": ["get_system_cpu_usage"]},
        "system information": {"system information": ["get_system_info"]},
        "system info": {"system info": ["get_system_info"]},
        "hostname": {"hostname": ["get_hostname"]},
        "network interfaces": {"network interfaces": ["get_network_interfaces"]},
        "calculator": {"calculator": ["calculator"]},
        "calculate": {"calculate": ["calculator"]},
        "arithmetic": {"arithmetic": ["calculator"]},
        "capabilities": {"capabilities": ["capability_inventory"]},
        "self-test": {"self-test": ["self_test"]},
        "self test": {"self test": ["self_test"]},
    }

    matches = []
    for phrase, mapping in capability_phrases.items():
        if phrase in text:
            for names in mapping.values():
                matches.extend(names)

    if matches:
        unique = list(dict.fromkeys(matches))
        return f"Capability match: {', '.join(unique)}."

    return (
        "Capability gap: no plausible local capability matches this request. "
        "Nova must not invent a tool or pretend the capability exists."
    )


def plan_capability_extension(request: str, inspect_reality: bool = False) -> str:
    """Create a bounded implementation plan, optionally grounded in current Android reality."""
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Request cannot be empty.")

    gap = assess_capability_gap(request)
    if gap.startswith("Capability match:"):
        return f"Extension not needed: {gap}"

    normalized = re.sub(r"[^a-z0-9]+", " ", request.lower()).strip()

    # Prefer stable semantic names for common requests instead of deriving a
    # tool name from model-generated filler such as "add a capability to".
    canonical_capabilities = (
        (("camera shutter", "capture a photo", "take a photo", "open the device camera", "open device camera"),
         "camera_shutter"),
    )
    for phrases, suffix in canonical_capabilities:
        if any(phrase in normalized for phrase in phrases):
            tool_name = f"extend_{suffix}"
            break
    else:
        words = [word for word in normalized.split() if word not in {
            "the", "a", "an", "to", "of", "do", "i", "have", "can", "you",
            "capability", "capabilities", "control", "phone", "add",
            "device", "open", "this",
        }]
        suffix = "_".join(words[:5]) or "requested_capability"
        tool_name = f"extend_{suffix}"

    if not inspect_reality:
        return (
            "Extension plan: capability is missing.\n"
            f"Requested capability: {request.strip()}\n"
            f"Proposed tool: {tool_name}\n"
            "Implementation boundary: inspect Android reality before committing to a mechanism; "
            "do not assume an API, permission, executable, or service exists.\n"
            "Implementation steps: discover the narrowest supported mechanism; implement a bounded "
            "tool with explicit inputs and safety checks; register its declaration and handler; "
            "add deterministic unit tests; run the real-device test; only then expose the capability to Nova.\n"
            "Verification: execute the new capability on the device and verify the resulting state or observable output.\n"
            "Status: plan only; no code or device state was modified."
        )

    # Ground the plan in current Android reality before proposing implementation.
    # Discovery and validation are read-only, so a plan request cannot mutate state.
    try:
        discovery = discover_android_mechanisms(request)
    except (RuntimeError, ValueError) as exc:
        return (
            "Extension plan: capability is missing.\n"
            f"Requested capability: {request.strip()}\n"
            f"Proposed tool: {tool_name}\n"
            f"Reality inspection: unavailable: {exc}\n"
            "Status: plan only; no code or device state was modified."
        )

    candidates = re.findall(r"(?m)^(intent|ui-text|ui):(.+)$", discovery)
    ranked = rank_android_mechanism_candidates(
        request,
        [f"{kind}:{value.strip()}" for kind, value in candidates],
    )
    viable = []
    validation_errors = []
    for mechanism in ranked:
        try:
            validation = validate_android_mechanism(request, mechanism)
        except (RuntimeError, ValueError) as exc:
            validation_errors.append(f"{mechanism}: {exc}")
            continue
        if "Status: VIABLE" in validation:
            viable.append(mechanism)
            break

    lines = [
        "Extension plan: capability is missing.",
        f"Requested capability: {request.strip()}",
        f"Proposed tool: {tool_name}",
        "Reality inspection: performed read-only before implementation.",
    ]
    if viable:
        lines.append("Viable discovered mechanisms:")
        lines.extend(f"- {mechanism}" for mechanism in viable[:10])
        lines.append(
            f"Preferred implementation mechanism: {viable[0]}"
        )
    else:
        lines.append("Viable discovered mechanisms: none.")
        if validation_errors:
            lines.append("Validation observations:")
            lines.extend(f"- {error}" for error in validation_errors[:10])
    lines.extend([
        "Implementation boundary: use only a mechanism grounded in current environment evidence; "
        "do not assume an API, permission, executable, or service exists.",
        "Implementation steps: implement a bounded tool with explicit inputs and safety checks; "
        "register its declaration and handler; add deterministic unit tests; run the real-device "
        "test; only then expose the capability to Nova.",
        "Verification: execute the new capability on the device and verify the resulting state or observable output.",
        "Status: plan only; no code or device state was modified.",
    ])
    return "\n".join(lines)


def _run_extension_test_suite() -> tuple[bool, str]:
    """Run Nova's deterministic test suite as part of an extension transaction."""
    try:
        completed = subprocess.run(
            [os.sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_gemini_*.py", "-q"],
            cwd=_filesystem_root(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "Extension verification failed: deterministic test suite timed out after 30 seconds."
    except OSError as exc:
        return False, f"Extension verification failed: could not start deterministic test suite: {exc}"

    output = (completed.stdout or "").strip()
    if completed.returncode != 0:
        if len(output) > 4096:
            output = output[-4096:]
        return False, f"Extension verification failed: deterministic test suite failed.\n{output}"
    return True, "Extension verification: deterministic test suite passed."


def _extension_registered_capability_error(original: str, updated: str, request: str) -> str | None:
    """Reject source edits that declare a new tool without implementing it."""
    plan = plan_capability_extension(request, inspect_reality=False)
    prefix = "Proposed tool: "
    if prefix not in plan:
        return "Extension not applied: could not determine the proposed capability name."
    proposed = plan.split(prefix, 1)[1].splitlines()[0].strip()
    if proposed.startswith("extend_"):
        proposed = proposed[len("extend_"):]
    if not proposed:
        return "Extension not applied: proposed capability name is empty."

    def source_names(source: str) -> set[str]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return set()
        names = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(node.name)
        return names

    def literal_tool_names(source: str) -> set[str]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return set()
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant) and key.value == "name":
                        if isinstance(value, ast.Constant) and isinstance(value.value, str):
                            names.add(value.value)
        return names

    def handler_keys(source: str) -> set[str]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return set()
        keys = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                targets = node.targets
                value = node.value
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
                value = node.value
            else:
                continue
            if not any(
                isinstance(target, ast.Name) and target.id == "TOOL_HANDLERS"
                for target in targets
            ):
                continue
            if isinstance(value, ast.Dict):
                for key in value.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        keys.add(key.value)
        return keys

    before_names = literal_tool_names(original)
    after_names = literal_tool_names(updated)
    added_names = after_names - before_names
    if proposed not in added_names:
        return (
            f"Extension not applied: proposed capability '{proposed}' was not added "
            "as a new tool declaration."
        )

    functions = source_names(updated)
    handlers = handler_keys(updated)
    missing = []
    if proposed not in functions:
        missing.append("implementation function")
    if proposed not in handlers:
        missing.append("TOOL_HANDLERS registration")
    if missing:
        return (
            f"Extension not applied: capability '{proposed}' is declared but missing "
            + " and ".join(missing)
            + ". A declaration alone is not an implementation."
        )
    return None


def _normalize_extension_fragment(fragment: str) -> str:
    """Normalize model-copied source excerpts without changing source semantics."""
    value = fragment.replace("\r\n", "\n").replace("\r", "\n")
    lines = value.split("\n")
    normalized = []
    for line in lines:
        match = re.match(r"^\s*\d+: ?(.*)$", line)
        normalized.append(match.group(1) if match else line)
    return "\n".join(normalized)

def _normalize_android_mechanism_target(target: str) -> str:
    """Normalize model formatting around a discovered bounded Android mechanism."""
    value = str(target).replace("\r\n", "\n").replace("\r", "\n").strip()
    value = value.strip(chr(96)).strip().strip(chr(34)).strip(chr(39)).strip()
    match = re.search(
        r"(intent|ui-text|ui)\s*:\s*(.+)",
        value,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        value = f"{match.group(1).lower()}:{match.group(2).strip()}"
    return value.strip(chr(96)).strip().strip(chr(34)).strip(chr(39)).strip()


def _extension_store_path() -> Path:
    """Return the local persistent store for self-generated capability metadata."""
    configured = os.environ.get("NOVA_CAPABILITY_STORE", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".nova-agent-capabilities.json"


def _persist_capability_extension(
    name: str,
    description: str,
    implementation_kind: str,
    implementation_target: str,
    implementation_args: str,
    request: str,
) -> None:
    """Atomically persist a verified generated capability outside the Git working tree."""
    path = _extension_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Capability store could not be read: {exc}") from exc
        if not isinstance(loaded, list):
            raise RuntimeError("Capability store must contain a JSON list.")
        entries = loaded
    entry = {
        "name": name,
        "description": description,
        "implementation_kind": implementation_kind,
        "implementation_target": implementation_target,
        "implementation_args": implementation_args,
        "request": request,
    }
    entries = [item for item in entries if not isinstance(item, dict) or item.get("name") != name]
    entries.append(entry)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(entries, temporary, ensure_ascii=False, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
    except OSError as exc:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise RuntimeError(f"Capability store write failed: {exc}") from exc


def apply_capability_extension(
    request: str,
    path: str,
    implementation_kind: str,
    implementation_target: str,
    implementation_args: str,
    declaration_description: str,
) -> str:
    """Apply a bounded extension built only from an existing local primitive."""
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Request cannot be empty.")
    if not isinstance(path, str) or not path.strip():
        raise ValueError("Path cannot be empty.")
    if not isinstance(implementation_kind, str) or not implementation_kind.strip():
        raise ValueError("Implementation kind cannot be empty.")
    if not isinstance(implementation_target, str) or not implementation_target.strip():
        raise ValueError("Implementation target cannot be empty.")
    if not isinstance(implementation_args, str):
        raise ValueError("Implementation args must be text.")
    if not isinstance(declaration_description, str) or not declaration_description.strip():
        raise ValueError("Declaration description cannot be empty.")
    if any(ord(char) < 32 and char not in "\t" for char in declaration_description):
        return "Extension not applied: declaration description contains unsupported control characters."

    gap = assess_capability_gap(request)
    if not gap.startswith("Capability gap:"):
        return f"Extension not applied: {gap}"

    plan = plan_capability_extension(request, inspect_reality=False)
    if plan.startswith("Extension not needed:"):
        return f"Extension not applied: {plan}"

    target = _safe_path(path)
    relative = target.relative_to(_filesystem_root()).as_posix()
    if relative != "gemini_agent/tools.py":
        raise ValueError("Structured capability extensions must target gemini_agent/tools.py.")
    if not target.exists() or not target.is_file() or target.is_symlink():
        return f"Extension not applied: target is not a regular source file: {relative}"

    plan = plan_capability_extension(request, inspect_reality=False)
    if plan.startswith("Extension blocked:"):
        return plan
    proposed = plan.split("Proposed tool: ", 1)[1].splitlines()[0].strip()
    if proposed.startswith("extend_"):
        proposed = proposed[len("extend_"):]

    kind = implementation_kind.strip().lower()
    target_name = implementation_target.strip()
    if kind == "android_mechanism":
        target_name = _normalize_android_mechanism_target(target_name)
    if kind not in {"existing_tool", "android_mechanism"}:
        return (
            "Extension not applied: implementation_kind must be 'existing_tool' "
            "or 'android_mechanism'."
        )
    if target_name == proposed:
        return "Extension not applied: extension target must not be the new capability itself."

    if kind == "android_mechanism":
        if not re.fullmatch(r"(?:intent|ui|ui-text):[^\s,]+", target_name, re.IGNORECASE):
            return (
                "Extension not applied: android_mechanism target must use a bounded "
                "intent:<action>, ui:<resource-id>, or ui-text:<text> mechanism."
            )
        if implementation_args.strip() not in {"", "{}"}:
            return (
                "Extension not applied: android_mechanism extensions do not accept "
                "implementation arguments; use {}."
            )
        validation = validate_android_mechanism(request, target_name)
        if "Status: VIABLE" not in validation:
            return (
                "Extension not applied: discovered Android mechanism is not viable.\n"
                + validation
            )
    else:
        available_targets = set(TOOL_HANDLERS)
        if target_name not in available_targets:
            available = ", ".join(sorted(available_targets))
            return (
                f"Extension not applied: existing local tool '{target_name}' is not available. "
                f"Valid implementation targets are: {available}"
            )
        extension_only_tools = {
            "assess_capability_gap",
            "plan_capability_extension",
            "apply_capability_extension",
            "capability_inventory",
            "self_test",
            "discover_camera_control",
            "find_executable",
            "diagnose_command_failure",
            "verify_command_result",
        }
        if target_name in extension_only_tools:
            return (
                f"Extension blocked: '{target_name}' is an inspection or orchestration tool, "
                "not an implementation primitive. Nova must choose an action-capable local "
                "primitive discovered in the environment."
            )

        try:
            primitive_signature = inspect.signature(TOOL_HANDLERS[target_name])
        except (TypeError, ValueError) as exc:
            return f"Extension not applied: could not inspect primitive '{target_name}': {exc}"

        try:
            parsed_arguments = json.loads(implementation_args.strip()) if implementation_args.strip() else {}
        except json.JSONDecodeError as exc:
            return f"Extension not applied: implementation_args is not valid JSON: {exc}"
        if not isinstance(parsed_arguments, dict):
            return "Extension not applied: implementation_args must decode to a JSON object."

        try:
            primitive_signature.bind(**parsed_arguments)
        except TypeError as exc:
            return (
                f"Extension not applied: arguments do not match existing primitive "
                f"'{target_name}': {exc}"
            )

    original = target.read_text(encoding="utf-8")
    try:
        tree = ast.parse(original, filename=relative)
    except SyntaxError as exc:
        return f"Extension not applied: existing source is invalid Python: {exc}"

    existing_functions = {
        node.name for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if proposed in existing_functions:
        return f"Extension not applied: capability function '{proposed}' already exists."

    declaration_marker = "TOOL_DECLARATIONS = ["
    handler_marker = "TOOL_HANDLERS: dict[str, Callable[..., str]] = {"

    # Generate the wrapper from an AST so model-supplied text cannot corrupt Python syntax.
    if kind == "android_mechanism":
        call = ast.Call(
            func=ast.Name(id="_run_android_mechanism_extension", ctx=ast.Load()),
            args=[ast.Constant(value=request.strip()), ast.Constant(value=target_name)],
            keywords=[],
        )
    else:
        call = ast.Call(
            func=ast.Name(id="_run_extension_primitive", ctx=ast.Load()),
            args=[ast.Constant(value=target_name), ast.Constant(value=implementation_args.strip())],
            keywords=[],
        )

    function_node = ast.FunctionDef(
        name=proposed,
        args=ast.arguments(
            posonlyargs=[],
            args=[],
            kwonlyargs=[],
            kw_defaults=[],
            defaults=[],
        ),
        body=[ast.Return(value=call)],
        decorator_list=[],
        returns=ast.Name(id="str", ctx=ast.Load()),
    )
    function_source = ast.unparse(ast.fix_missing_locations(function_node))
    function_source += (
        f"\n{proposed}.__nova_generated_capability__ = True"
    )

    declaration = (
        "    {\n"
        f'        "name": "{proposed}",\n'
        f'        "description": {declaration_description.strip()!r},\n'
        '        "parameters": {"type": "OBJECT", "properties": {}},\n'
        "    },\n"
    )
    handler_line = f'    "{proposed}": {proposed},\n'

    declaration_index = original.find(declaration_marker)
    handler_index = original.find(handler_marker)
    if declaration_index < 0 or handler_index < 0:
        return "Extension not applied: required top-level tool integration anchors were not found."

    declaration_end = original.find("\n]\n", declaration_index)
    if declaration_end < 0:
        return "Extension not applied: TOOL_DECLARATIONS closing anchor was not found."
    updated = (
        original[:declaration_end]
        + "\n"
        + declaration.rstrip("\n")
        + original[declaration_end:]
    )

    handler_index = updated.rfind(handler_marker)
    handler_end = updated.find("\n}\n", handler_index)
    if handler_index < 0 or handler_end < 0:
        return "Extension not applied: TOOL_HANDLERS closing anchor was not found."
    updated = (
        updated[:handler_end]
        + "\n"
        + handler_line.rstrip("\n")
        + updated[handler_end:]
    )

    helper_source = """\n\ndef _run_extension_primitive(tool_name: str, arguments: str) -> str:
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        raise ValueError(f"Unknown extension primitive: {tool_name}")
    parsed = json.loads(arguments) if arguments.strip() else {}
    if not isinstance(parsed, dict):
        raise ValueError("Extension primitive arguments must be a JSON object.")
    return str(handler(**parsed))

def _run_android_mechanism_extension(request: str, mechanism: str) -> str:
    validation = validate_android_mechanism(request, mechanism)
    if "Status: VIABLE" not in validation:
        return "Extension capability blocked: Android mechanism is no longer viable.\\n" + validation
    if mechanism.lower().startswith(("ui:", "ui-text:")):
        from gemini_agent.android_ui import execute_validated_android_ui_mechanism
        return str(execute_validated_android_ui_mechanism(request=request, mechanism=mechanism))
    return str(execute_validated_android_mechanism(request=request, mechanism=mechanism))
"""
    helper_insert = helper_source if "def _run_extension_primitive" not in updated else ""
    handler_insert_index = updated.rfind(handler_marker)
    if handler_insert_index < 0:
        return "Extension not applied: implementation insertion anchor was not found."
    updated = (
        updated[:handler_insert_index]
        + "\n"
        + function_source
        + helper_insert
        + "\n"
        + updated[handler_insert_index:]
    )

    try:
        ast.parse(updated, filename=relative)
    except SyntaxError as exc:
        generated_lines = updated.splitlines()
        line = generated_lines[exc.lineno - 1] if exc.lineno and 0 < exc.lineno <= len(generated_lines) else "<unavailable>"
        return (
            "Extension not applied: internally generated source is invalid Python: "
            f"{exc}. Offending line: {line!r}"
        )

    registration_error = _extension_registered_capability_error(original, updated, request)
    if registration_error:
        return registration_error

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.extension-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(updated)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, target)
    except OSError as exc:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        return f"Extension not applied: source write failed: {exc}"

    passed, verification = _run_extension_test_suite()
    if not passed:
        try:
            target.write_text(original, encoding="utf-8")
        except OSError as exc:
            return f"Extension transaction failed and rollback failed for {relative}: {exc}\n{verification}"
        return f"Extension rolled back: {verification}"

    try:
        _persist_capability_extension(
            proposed,
            declaration_description.strip(),
            kind,
            target_name,
            implementation_args.strip(),
            request.strip(),
        )
    except RuntimeError as exc:
        try:
            target.write_text(original, encoding="utf-8")
        except OSError as rollback_exc:
            return (
                f"Extension persistence failed and rollback failed for {relative}: "
                f"{rollback_exc}\n{exc}"
            )
        return f"Extension rolled back: persistence failed: {exc}"

    return (
        f"Edited {relative}\n"
        "Extension status: source edit applied and transaction committed.\n"
        f"{verification}\n"
        "Real-device verification status: not yet verified; do not expose the new capability until the device test passes."
    )

def self_test() -> str:
    """Run a small deterministic health check of Nova's local execution substrate."""
    checks = []
    failures = []

    def check(name: str, condition: bool) -> None:
        if condition:
            checks.append(name)
        else:
            failures.append(name)

    try:
        check("calculator", calculator("2 + 3 * 4") == "14")
    except Exception:
        failures.append("calculator")

    try:
        value = current_datetime()
        dt.datetime.fromisoformat(value)
        check("datetime", True)
    except Exception:
        failures.append("datetime")

    try:
        check("filesystem_root", path_exists(".") == "true")
    except Exception:
        failures.append("filesystem_root")

    try:
        discovered = find_executable(Path(os.sys.executable).name)
        check("executable_discovery", discovered.startswith("Executable: "))
    except Exception:
        failures.append("executable_discovery")

    try:
        diagnosis = diagnose_command_failure("missing", "command not found")
        check("failure_diagnosis", "find_executable" in diagnosis)
    except Exception:
        failures.append("failure_diagnosis")

    total = len(checks) + len(failures)
    if failures:
        return f"Self-test: FAIL ({len(checks)}/{total} passed)\nFailed: {', '.join(failures)}"
    return f"Self-test: PASS ({len(checks)}/{total} checks passed)"


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
    re.compile(r"^dumpsys(?:\s+[A-Za-z0-9_.-]+(?:\s+[^;&|$]+)?)?$"),
    re.compile(r"^cmd\s+package\s+resolve-activity\s+--brief\s+-a\s+android\.media\.action\.IMAGE_CAPTURE$"),
    re.compile(r"^cmd\s+package\s+resolve-activity\s+--brief\s+-a\s+android\.media\.action\.STILL_IMAGE_CAMERA$"),
    re.compile(r"^uiautomator\s+dump\s+/dev/tty$"),
    re.compile(r"^uiautomator\s+dump\s+/data/local/tmp/nova-ui-hierarchy\.xml$"),
    re.compile(r"^cat\s+/data/local/tmp/nova-ui-hierarchy\.xml$"),
    re.compile(r"^rm\s+-f\s+/data/local/tmp/nova-ui-hierarchy\.xml$"),
    re.compile(r"^uiautomator\s+dump\s+/data/local/tmp/nova-ui-validation\.xml$"),
    re.compile(r"^cat\s+/data/local/tmp/nova-ui-validation\.xml$"),
    re.compile(r"^rm\s+-f\s+/data/local/tmp/nova-ui-validation\.xml$"),
    re.compile(r"^uiautomator\s+dump\s+/data/local/tmp/nova-ui-execution\.xml$"),
    re.compile(r"^cat\s+/data/local/tmp/nova-ui-execution\.xml$"),
    re.compile(r"^rm\s+-f\s+/data/local/tmp/nova-ui-execution\.xml$"),
    re.compile(r"^uiautomator\s+dump\s+/data/local/tmp/nova-ui-actions\.xml$"),
    re.compile(r"^cat\s+/data/local/tmp/nova-ui-actions\.xml$"),
    re.compile(r"^rm\s+-f\s+/data/local/tmp/nova-ui-actions\.xml$"),
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
    if "command is not allowed" in text or "not allowed:" in text:
        return "Diagnosis: command is blocked by Nova's normal execution policy. Next: discover the executable and use the narrowest approved privileged workflow when the command is a safe Android diagnostic."
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
    if executable not in _RUN_COMMAND_ALLOWED:
        raise ValueError(f"Command is not allowed: {executable}")
    if "/" in parts[0]:
        resolved = os.path.realpath(parts[0])
        discovered = find_executable(executable)
        if discovered != f"Executable: {resolved}":
            raise ValueError(f"Executable path is not the discovered path: {parts[0]}")
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


def _run_bounded_ui_tap(x: int, y: int) -> str:
    """Tap one validated UI coordinate through the manually entered root shell."""
    if not isinstance(x, int) or not isinstance(y, int):
        raise ValueError("UI tap coordinates must be integers.")
    if x < 0 or y < 0 or x > 10000 or y > 10000:
        raise ValueError("UI tap coordinates are outside the bounded screen range.")
    return _run_bounded_root_action(f"input tap {x} {y}")


def _run_bounded_root_action(command: str) -> str:
    """Run one explicitly allowlisted Android action inside a root shell."""
    allowed_commands = {
        "input keyevent 3",
        "input keyevent 4",
        "input keyevent 25",
        "input keyevent 27",
        "am start -a android.media.action.IMAGE_CAPTURE",
        "am start -a android.media.action.STILL_IMAGE_CAMERA",
    }
    if command not in allowed_commands and not re.fullmatch(r"input tap (?:[0-9]|[1-9][0-9]{1,3}|10000) (?:[0-9]|[1-9][0-9]{1,3}|10000)", command):
        raise ValueError("Root action is not allowed.")
    try:
        completed = subprocess.run(
            ["su"],
            input=command + "\nexit\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=_ROOT_COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Root action timed out after {_ROOT_COMMAND_TIMEOUT_SECONDS} seconds.") from exc
    except OSError as exc:
        raise RuntimeError(f"Root action failed to start: {exc}") from exc

    stdout = (completed.stdout or "").encode("utf-8", errors="replace")[:_ROOT_COMMAND_OUTPUT_BYTES].decode("utf-8", errors="ignore").rstrip()
    stderr = (completed.stderr or "").encode("utf-8", errors="replace")[:_ROOT_COMMAND_OUTPUT_BYTES].decode("utf-8", errors="ignore").rstrip()
    result = f"Exit code: {completed.returncode}"
    if stdout:
        result += f"\nstdout:\n{stdout}"
    if stderr:
        result += f"\nstderr:\n{stderr}"
    return result


def _dump_camera_ui_hierarchy() -> str:
    """Dump the foreground Android UI hierarchy through a bounded temporary file."""
    path = "/data/local/tmp/nova_camera_ui.xml"
    dump_command = f"uiautomator dump {path}"
    read_command = f"cat {path}"
    cleanup_command = f"rm -f {path}"
    try:
        completed = subprocess.run(
            ["su"],
            input=dump_command + "\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=8,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Camera UI hierarchy dump timed out after 8 seconds.") from exc
    except OSError as exc:
        raise RuntimeError(f"Camera UI hierarchy dump failed to start: {exc}") from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(
            "Camera UI hierarchy dump failed"
            + (f": {detail}" if detail else ".")
        )

    try:
        completed = subprocess.run(
            ["su"],
            input=read_command + "\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Camera UI hierarchy read timed out after 5 seconds.") from exc
    except OSError as exc:
        raise RuntimeError(f"Camera UI hierarchy read failed to start: {exc}") from exc
    finally:
        try:
            subprocess.run(
                ["su"],
                input=cleanup_command + "\n",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(
            "Camera UI hierarchy read failed"
            + (f": {detail}" if detail else ".")
        )

    output = (completed.stdout or "").encode("utf-8", errors="replace")
    if len(output) > _ROOT_COMMAND_OUTPUT_BYTES:
        output = output[:_ROOT_COMMAND_OUTPUT_BYTES] + b"\n[output truncated]"
    return output.decode("utf-8", errors="ignore").rstrip()


def _read_bounded_root_file(path: str, max_bytes: int) -> str:
    """Read one allowlisted root-owned diagnostic file with a bounded size."""
    allowed_paths = {
        "/data/local/tmp/nova-ui-actions.xml",
        "/data/local/tmp/nova-ui-validation.xml",
        "/data/local/tmp/nova-ui-execution.xml",
        "/data/local/tmp/nova-ui-hierarchy.xml",
    }
    if path not in allowed_paths:
        raise ValueError("Root file path is not allowed.")
    if not isinstance(max_bytes, int) or max_bytes <= 0 or max_bytes > 64 * 1024:
        raise ValueError("Invalid bounded read size.")
    try:
        completed = subprocess.run(
            ["su"],
            input=f"cat {path}\n".encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            timeout=_ROOT_COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Bounded root file read timed out.") from exc
    except OSError as exc:
        raise RuntimeError(f"Bounded root file read failed to start: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Bounded root file read failed{': ' + detail if detail else '.'}")
    data = completed.stdout[:max_bytes]
    if len(completed.stdout) > max_bytes:
        raise RuntimeError("UI hierarchy exceeds the bounded parsing size.")
    return data.decode("utf-8", errors="strict")


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



def recover_command(command: str, expected: str = "") -> str:
    """Execute an approved command, recover once when needed, and optionally verify a postcondition."""
    if not isinstance(command, str) or not command.strip():
        raise ValueError("Command cannot be empty.")
    if not isinstance(expected, str):
        raise ValueError("Expected postcondition must be text.")
    expected = expected.strip()

    def outcome(result: str) -> str:
        if not result.startswith("Exit code: 0"):
            return "FAILED"
        if expected and expected not in result:
            return "FAILED"
        return "VERIFIED" if expected else "SUCCEEDED"

    def postcondition_evidence(result: str) -> str:
        if not expected:
            return ""
        if result.startswith("Exit code: 0") and expected in result:
            return f"Postcondition: VERIFIED: expected text found: {expected}"
        return f"Postcondition: FAILED: expected text not found: {expected}"

    def format_result(prefix: str, result: str) -> str:
        status = outcome(result)
        evidence = postcondition_evidence(result)
        return f"{prefix}\nOutcome: {status}\n{result}" + (f"\n{evidence}" if evidence else "")

    def format_recovery_attempts(
        first_result: str,
        second_result: str,
        recovery_reason: str,
    ) -> str:
        first_status = outcome(first_result)
        second_status = outcome(second_result)
        first_evidence = postcondition_evidence(first_result)
        second_evidence = postcondition_evidence(second_result)
        lines = [
            f"First attempt: {first_status}",
            first_result,
        ]
        if first_evidence:
            lines.append(first_evidence)
        lines.extend([
            recovery_reason,
            "Attempts: 2",
            f"Second attempt: {second_status}",
            second_result,
        ])
        if second_evidence:
            lines.append(second_evidence)
        lines.append(f"Outcome: {second_status}")
        return "\n".join(lines)

    try:
        first_result = run_command(command)
    except (RuntimeError, ValueError) as exc:
        first_result = f"Tool error: {exc}"

    if first_result.startswith("Exit code: 0"):
        if expected and expected not in first_result:
            try:
                recovery_result = run_command(command)
            except (RuntimeError, ValueError) as exc:
                recovery_result = f"Tool error: {exc}"
            return format_recovery_attempts(
                first_result,
                recovery_result,
                "Recovery: command exited successfully but its postcondition was not verified; retried once.",
            )
        return format_result("Recovery: none needed.\nAttempts: 1", first_result)

    diagnosis = diagnose_command_failure(command, first_result)
    lowered = first_result.lower()

    if "timed out" in lowered:
        try:
            retry_result = run_command(command)
        except (RuntimeError, ValueError) as exc:
            retry_result = f"Tool error: {exc}"
        return diagnosis + "\n" + format_recovery_attempts(
            first_result,
            retry_result,
            "Recovery: command timed out; retried once.",
        )

    parts = shlex.split(command)
    executable = Path(parts[0]).name
    if any(term in lowered for term in (
        "not found",
        "no such file or directory",
        "command not found",
        "command is not allowed",
    )):
        discovered = find_executable(executable)
        if discovered.startswith("Executable: "):
            discovered_path = discovered.removeprefix("Executable: ")
            root_safe = any(
                pattern.fullmatch(command.strip())
                for pattern in _ROOT_DIAGNOSTIC_PATTERNS
            )
            if root_safe:
                try:
                    root_result = run_root_command(command)
                except (RuntimeError, ValueError) as exc:
                    if command.strip() == "dumpsys" and "timed out" in str(exc).lower():
                        try:
                            root_result = run_root_command("dumpsys -l")
                        except (RuntimeError, ValueError) as retry_exc:
                            root_result = f"Tool error: {retry_exc}"
                        if outcome(root_result) in ("SUCCEEDED", "VERIFIED"):
                            return diagnosis + "\nRecovery: bare dumpsys was unbounded; adapted to the bounded manual-su service-list diagnostic and command succeeded.\n" + format_result("Attempts: 2", root_result)
                        return diagnosis + "\nRecovery: bare dumpsys was unbounded; bounded manual-su diagnostic also failed.\n" + format_result("Attempts: 2", root_result)
                    root_result = f"Tool error: {exc}"
                if outcome(root_result) in ("SUCCEEDED", "VERIFIED"):
                    return diagnosis + "\nRecovery: executable discovered; used the manual-su root workflow.\n" + format_result("Attempts: 2", root_result)
                return diagnosis + "\nRecovery: executable discovered; root workflow attempted but command failed.\n" + format_result("Attempts: 2", root_result)

            recovered_command = " ".join(
                [shlex.quote(discovered_path), *(shlex.quote(part) for part in parts[1:])]
            )
            try:
                recovered_result = run_command(recovered_command)
            except (RuntimeError, ValueError) as exc:
                recovered_result = f"Recovery execution failed: {exc}"
            if outcome(recovered_result) in ("SUCCEEDED", "VERIFIED"):
                return diagnosis + "\nRecovery: executable path discovered and command succeeded.\n" + format_result("Attempts: 2", recovered_result)
            return diagnosis + "\nRecovery: executable path discovered but corrected command failed.\n" + format_result("Attempts: 2", recovered_result)
        return diagnosis + "\n" + discovered + "\nOutcome: FAILED"

    return diagnosis + "\nRecovery: no automatic retry performed.\nOutcome: FAILED"

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
    "description": "Execute one approved command, apply one safe diagnostic recovery step when it fails, and optionally verify an expected postcondition. If the user explicitly supplies or requires expected/postcondition text, you MUST pass that text in the expected argument. Do not omit it and do not treat exit code alone as proof of success.",
    "parameters": {"type": "OBJECT", "properties": {
        "command": {"type": "STRING", "description": "Approved command and arguments to execute."},
        "expected": {"type": "STRING", "description": "Optional exact text that must appear in the final result to verify the requested postcondition."},
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
        "name": "select_capability_repair_candidate",
        "description": "Select a bounded repair candidate from read-only capability registration and persisted-recipe evidence. Do not execute or modify the capability.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "capability": {"type": "STRING", "description": "Name of the local capability reported as failing."},
                "diagnosis": {"type": "STRING", "description": "Read-only diagnosis result for the capability failure."},
            },
            "required": ["capability", "diagnosis"],
        },
    },
    {
        "name": "diagnose_capability_failure",
        "description": "Diagnose a reported local capability failure using read-only registration and repair-recipe evidence. Do not execute or modify the capability.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "capability": {"type": "STRING", "description": "Name of the local capability reported as failing."},
                "failure_evidence": {"type": "STRING", "description": "Observed or supplied evidence that the capability failed."},
            },
            "required": ["capability", "failure_evidence"],
        },
    },
    {
        "name": "recover_android_mechanism",
        "description": "Diagnose an Android mechanism outcome and perform generic recovery/replanning only when bounded evidence justifies another mechanism.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "request": {"type": "STRING", "description": "Original capability request."},
                "mechanism": {"type": "STRING", "description": "Executed Android mechanism."},
                "verification": {"type": "STRING", "description": "Observed post-action verification result."},
            },
            "required": ["request", "mechanism", "verification"],
        },
    },
    {
        "name": "diagnose_android_mechanism_outcome",
        "description": "Diagnose inconclusive or failed Android mechanism outcomes using bounded read-only evidence.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "request": {"type": "STRING", "description": "Original capability request."},
                "mechanism": {"type": "STRING", "description": "Executed Android mechanism."},
                "verification": {"type": "STRING", "description": "Observed post-action verification result."},
            },
            "required": ["request", "mechanism", "verification"],
        },
    },
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
        "name": "discover_android_mechanisms",
        "description": "Discover safe, read-only Android executables, services, and bounded intent mechanisms that may implement a missing capability. Intent candidates are resolved only; no action is performed.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "request": {"type": "STRING", "description": "The capability whose Android implementation mechanisms should be discovered."}
            },
            "required": ["request"],
        },
    },
    {
        "name": "execute_validated_android_mechanism",
        "description": "Execute a previously validated Android intent mechanism through a bounded action primitive. Unsupported mechanism types are blocked.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "request": {"type": "STRING", "description": "The capability the validated mechanism implements."},
                "mechanism": {"type": "STRING", "description": "Previously validated mechanism in intent:<action> form."},
            },
            "required": ["request", "mechanism"],
        },
    },
    {
        "name": "execute_validated_android_ui_mechanism",
        "description": "Execute a previously validated Android UI mechanism by resolving its current UI node and performing one bounded tap. Supports ui:<resource-id> and ui-text:<text> selectors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "request": {"type": "STRING", "description": "The capability the validated UI mechanism implements."},
                "mechanism": {"type": "STRING", "description": "Previously validated UI mechanism in ui:<resource-id> or ui-text:<text> form."},
            },
            "required": ["request", "mechanism"],
        },
    },
    {
        "name": "validate_android_mechanism",
        "description": "Validate a discovered Android mechanism without executing the requested capability or changing device state.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "request": {"type": "STRING", "description": "The capability the mechanism is intended to implement."},
                "mechanism": {"type": "STRING", "description": "Bounded mechanism in intent:<action>, executable:<name>, service:<name>, or ui:<resource-id> form."},
            },
            "required": ["request", "mechanism"],
        },
    },
    {
        "name": "resolve_android_intent",
        "description": "Resolve an allowlisted Android intent without launching it. Use this to discover which activity would handle a mechanism before any action is performed.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Android intent action, currently IMAGE_CAPTURE or STILL_IMAGE_CAMERA.",
                }
            },
            "required": ["action"],
        },
    },
    {
        "name": "discover_camera_control",
        "description": "Inspect Android for safe, read-only mechanisms that could control the phone camera, without performing a camera action.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "send_android_keyevent",
        "description": "Send one bounded Android key event through the manually entered root shell. Supported actions: HOME, BACK, VOLUME_DOWN, CAMERA.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "keycode": {"type": "STRING", "description": "HOME, BACK, CAMERA, or Android keycode 3, 4, or 27."}
            },
            "required": ["keycode"],
        },
    },
    {
        "name": "get_foreground_android_component",
        "description": "Inspect the current foreground Android package and activity using read-only diagnostics without interacting with the device.",
        "parameters": {"type": "OBJECT", "properties": {}, "required": []},
    },
    {
        "name": "discover_android_ui_actions",
        "description": "Discover enabled clickable Android UI controls from the current UI hierarchy without interacting with the device.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "inspect_android_ui",
        "description": "Inspect the current foreground Android UI hierarchy using read-only diagnostics, optionally filtered to one ui:<resource-id> or ui-text:<text> selector.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "selector": {
                    "type": "STRING",
                    "description": "Optional UI selector to inspect one enabled node, using ui:<resource-id> or ui-text:<text>.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "send_android_intent",
        "description": "Launch one bounded Android intent action from Nova's allowlisted action set.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Android intent action, currently IMAGE_CAPTURE or android.media.action.IMAGE_CAPTURE.",
                }
            },
            "required": ["action"],
        },
    },

    {
        "name": "self_test",
        "description": "Run a small deterministic health check of Nova's local execution substrate without modifying user data.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "analyze_capability_history",
        "description": "Read persisted capability outcome history and make a bounded repair-verification decision without executing or modifying anything.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "capability": {"type": "STRING", "description": "Capability name whose persisted verification history should be analyzed."}
            },
            "required": ["capability"],
        },
    },
    {
        "name": "record_capability_repair_verification",
        "description": "Persist the latest bounded execution verification for a repaired generated capability while keeping the repair PENDING.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "capability": {"type": "STRING"},
                "verification": {"type": "STRING", "description": "Bounded verification evidence produced by the capability execution."},
            },
            "required": ["capability", "verification"],
        },
    },
    {
        "name": "accept_verified_capability_repair",
        "description": "Persist acceptance of a repaired generated capability after independently verified execution.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "capability": {"type": "STRING"},
                "verification": {"type": "STRING", "description": "Bounded verification evidence produced by the capability execution."},
            },
            "required": ["capability", "verification"],
        },
    },
    {
        "name": "apply_capability_repair",
        "description": "Apply a bounded repair transaction from a persisted verified capability recipe.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "capability": {"type": "STRING"},
                "candidate": {"type": "STRING"},
            },
            "required": ["capability", "candidate"],
        },
    },
    {
        "name": "capability_inventory",
        "description": "List the local tools Nova currently exposes and their purposes.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "assess_capability_gap",
        "description": "Determine whether Nova has a plausible local capability for a requested task, without inventing unsupported capabilities.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "request": {"type": "STRING", "description": "The capability the user is asking whether Nova has."}
            },
            "required": ["request"],
        },
    },
    {
        "name": "plan_capability_extension",
        "description": "Create a bounded implementation plan for a missing capability without modifying code or device state.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "request": {"type": "STRING", "description": "The missing capability to plan an extension for."}
            },
            "required": ["request"],
        },
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
        "name": "apply_capability_extension",
        "description": "Apply one bounded extension using either an existing local tool or a validated Android mechanism discovered in the environment. Nova generates the wrapper locally and never accepts model-generated Python source.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "request": {"type": "STRING", "description": "The missing capability being extended."},
                "path": {"type": "STRING", "description": "Use exactly gemini_agent/tools.py."},
                "implementation_kind": {"type": "STRING", "description": "Use existing_tool for a local primitive, or android_mechanism for a validated intent:<action>, ui:<resource-id>, or ui-text:<text> mechanism."},
                "implementation_target": {"type": "STRING", "description": "Existing TOOL_HANDLERS name, or the exact validated Android mechanism when using android_mechanism."},
                "implementation_args": {"type": "STRING", "description": "JSON arguments for existing_tool; use {} for android_mechanism."},
                "declaration_description": {"type": "STRING", "description": "Description for the new tool declaration."}
            },
            "required": ["request", "path", "implementation_kind", "implementation_target", "implementation_args", "declaration_description"],
        },
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

RECOVER_ANDROID_MECHANISM_DECLARATION = {
    "name": "recover_android_mechanism",
    "description": "Diagnose an Android mechanism outcome and perform generic recovery/replanning only when bounded evidence justifies another mechanism.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "request": {"type": "STRING", "description": "Original capability request."},
            "mechanism": {"type": "STRING", "description": "Executed Android mechanism."},
            "verification": {"type": "STRING", "description": "Observed post-action verification result."},
        },
        "required": ["request", "mechanism", "verification"],
    },
}

DIAGNOSE_ANDROID_MECHANISM_OUTCOME_DECLARATION = {
    "name": "diagnose_android_mechanism_outcome",
    "description": "Diagnose inconclusive or failed Android mechanism outcomes using bounded read-only evidence.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "request": {"type": "STRING", "description": "Original capability request."},
            "mechanism": {"type": "STRING", "description": "Executed Android mechanism."},
            "verification": {"type": "STRING", "description": "Observed post-action verification result."},
        },
        "required": ["request", "mechanism", "verification"],
    },
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
    "record_capability_repair_verification": record_capability_repair_verification,
    "analyze_capability_history": analyze_capability_history,
    "record_capability_outcome": record_capability_outcome,
    "get_capability_outcome_history": get_capability_outcome_history,
    "accept_verified_capability_repair": accept_verified_capability_repair,
    "select_capability_repair_candidate": select_capability_repair_candidate,
    "diagnose_capability_failure": diagnose_capability_failure,
    "diagnose_android_mechanism_outcome": diagnose_android_mechanism_outcome,
    "recover_android_mechanism": recover_android_mechanism,
    "execute_android_mechanism": execute_android_mechanism,
    "execute_validated_android_mechanism": execute_validated_android_mechanism,
    "execute_validated_android_ui_mechanism": execute_validated_android_ui_mechanism,
    "discover_android_mechanisms": discover_android_mechanisms,
    "validate_android_mechanism": validate_android_mechanism,
    "resolve_android_intent": resolve_android_intent,
    "discover_camera_control": discover_camera_control,
    "plan_capability_extension": plan_capability_extension,
    "apply_capability_extension": apply_capability_extension,
    "assess_capability_gap": assess_capability_gap,
    "capability_inventory": capability_inventory,
    "apply_capability_repair": apply_capability_repair,
    "self_test": self_test,
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
    "send_android_keyevent": send_android_keyevent,
    "inspect_android_ui": inspect_android_ui,
    "discover_android_ui_actions": discover_android_ui_actions,
    "get_foreground_android_component": get_foreground_android_component,
    "send_android_intent": send_android_intent,
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


def _run_extension_primitive(tool_name: str, arguments: str) -> str:
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        raise ValueError(f"Unknown extension primitive: {tool_name}")
    parsed = json.loads(arguments) if arguments.strip() else {}
    if not isinstance(parsed, dict):
        raise ValueError("Extension primitive arguments must be a JSON object.")
    return str(handler(**parsed))


def _run_android_mechanism_extension(request: str, mechanism: str) -> str:
    validation = validate_android_mechanism(request, mechanism)
    if "Status: VIABLE" not in validation:
        return "Extension capability blocked: Android mechanism is no longer viable.\n" + validation
    if mechanism.lower().startswith(("ui:", "ui-text:")):
        from gemini_agent.android_ui import execute_validated_android_ui_mechanism
        return str(
            execute_validated_android_ui_mechanism(
                request=request,
                mechanism=mechanism,
            )
        )
    return str(execute_validated_android_mechanism(request=request, mechanism=mechanism))



def _restore_persisted_capability_entry(entry: dict, *, replace_existing: bool = False) -> bool:
    """Restore one bounded persisted capability recipe without executing it."""
    if not isinstance(entry, dict):
        return False
    name = entry.get("name", "")
    description = entry.get("description", "")
    kind = entry.get("implementation_kind", "")
    target = entry.get("implementation_target", "")
    arguments = entry.get("implementation_args", "")
    request = entry.get("request", "")
    if (
        not isinstance(name, str)
        or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
        or (name in TOOL_HANDLERS and not replace_existing)
        or not isinstance(description, str)
        or not description.strip()
        or kind not in {"existing_tool", "android_mechanism"}
        or not isinstance(target, str)
        or not target.strip()
        or not isinstance(arguments, str)
        or not isinstance(request, str)
        or not request.strip()
    ):
        return False

    if kind == "android_mechanism":
        mechanism = target.strip()
        capability_request = request.strip()

        def restored_capability(
            _request: str = capability_request,
            _mechanism: str = mechanism,
        ) -> str:
            return str(_run_android_mechanism_extension(_request, _mechanism))
    else:
        primitive = target.strip()
        primitive_arguments = arguments.strip()
        if "_run_extension_primitive" not in globals():
            return False
        if primitive not in TOOL_HANDLERS:
            return False

        def restored_capability(
            _primitive: str = primitive,
            _arguments: str = primitive_arguments,
        ) -> str:
            return str(_run_extension_primitive(_primitive, _arguments))

    restored_capability.__name__ = name
    restored_capability.__qualname__ = name
    restored_capability.__nova_generated_capability__ = True
    TOOL_HANDLERS[name] = restored_capability
    TOOL_DECLARATIONS.append(
        {
            "name": name,
            "description": description.strip(),
            "parameters": {"type": "OBJECT", "properties": {}},
        }
    )
    return True


def _load_persisted_capability_extensions() -> list[dict]:
    """Restore verified self-generated capabilities and return their persisted recipes."""
    path = _extension_store_path()
    if not path.exists():
        return []
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(entries, list):
        return []

    for entry in entries:
        _restore_persisted_capability_entry(entry)
    return [entry for entry in entries if isinstance(entry, dict)]


_load_persisted_capability_extensions()
