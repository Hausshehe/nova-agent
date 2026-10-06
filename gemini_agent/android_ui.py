"""Bounded Android UI mechanism execution for Nova."""

import re
import time
import xml.etree.ElementTree as ET

from gemini_agent.tools import _read_bounded_root_file, _run_bounded_ui_tap, run_root_command, validate_android_mechanism


def _read_ui_target(xml_text: str, kind: str, selector: str):
    """Parse one uniquely enabled UI target from a bounded hierarchy snapshot."""
    root = ET.fromstring(xml_text)
    attribute = "resource-id" if kind == "ui" else "text"
    matches = [
        node for node in root.iter("node")
        if node.attrib.get(attribute, "") == selector
        and node.attrib.get("enabled") == "true"
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def execute_validated_android_ui_mechanism(request: str, mechanism: str) -> str:
    """Execute one validated UI mechanism by resource ID using current UI bounds."""
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Request cannot be empty.")
    if not isinstance(mechanism, str) or not mechanism.strip():
        raise ValueError("Mechanism cannot be empty.")

    candidate = mechanism.strip()
    if ":" not in candidate:
        raise ValueError("Mechanism must use a bounded form: ui:<resource-id> or ui-text:<text>.")

    kind, selector = candidate.split(":", 1)
    kind = kind.strip().lower()
    selector = selector.strip()
    if kind not in {"ui", "ui-text"}:
        raise ValueError(
            "This execution layer supports only validated ui:<resource-id> or ui-text:<text> mechanisms."
        )
    if not selector:
        raise ValueError("UI selector cannot be empty.")
    validation = validate_android_mechanism(request, candidate)
    if "Status: VIABLE" not in validation:
        return (
            "Android UI mechanism execution blocked: the mechanism did not validate as viable.\n"
            + validation
        )

    dump_path = "/data/local/tmp/nova-ui-execution.xml"
    try:
        def capture_hierarchy() -> str:
            dump_result = run_root_command(f"uiautomator dump {dump_path}")
            if not dump_result.startswith("Exit code: 0"):
                raise RuntimeError(dump_result)
            return _read_bounded_root_file(dump_path, 64 * 1024)

        try:
            xml_before = capture_hierarchy()
        except (RuntimeError, ValueError) as exc:
            return f"Android UI mechanism execution failed: UI hierarchy could not be captured: {exc}"

        try:
            target = _read_ui_target(xml_before, kind, selector)
        except ET.ParseError as exc:
            return f"Android UI mechanism execution failed: invalid UI hierarchy: {exc}"

        if target is None:
            return (
                "Android UI mechanism execution blocked: the validated control is not present "
                "as exactly one enabled UI node."
            )

        bounds = target.attrib.get("bounds", "")
        match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
        if not match:
            return "Android UI mechanism execution blocked: the target control has no usable bounds."

        left, top, right, bottom = map(int, match.groups())
        if right <= left or bottom <= top:
            return "Android UI mechanism execution blocked: target bounds are invalid."

        center_x = (left + right) // 2
        center_y = (top + bottom) // 2
        result = _run_bounded_ui_tap(center_x, center_y)

        try:
            xml_after = capture_hierarchy()
            after_target = _read_ui_target(xml_after, kind, selector)
        except (RuntimeError, ValueError, ET.ParseError) as exc:
            return (
                "Android UI mechanism execution:\n"
                f"Requested capability: {request.strip()}\n"
                f"Mechanism: {candidate}\n"
                "Validation: VIABLE\n"
                f"Resolved bounds: {bounds}\n"
                f"Tap result:\n{result}\n"
                f"Post-action verification: UNAVAILABLE ({exc})"
            )

        before_attrs = dict(target.attrib)
        after_attrs = dict(after_target.attrib) if after_target is not None else None
        tap_succeeded = re.search(r"(?m)^Exit code: 0(?:$|\\n)", result) is not None
        if after_attrs is not None and before_attrs != after_attrs:
            verification = "VERIFIED: target UI node attributes changed after the tap."
        elif after_attrs is None:
            verification = (
                "INCONCLUSIVE: target UI node was no longer uniquely present after the tap."
                if tap_succeeded
                else "FAILED: target UI node was no longer uniquely present after a failed tap."
            )
        elif tap_succeeded:
            time.sleep(0.25)
            try:
                xml_recheck = capture_hierarchy()
                recheck_target = _read_ui_target(xml_recheck, kind, selector)
            except (RuntimeError, ValueError, ET.ParseError) as exc:
                verification = (
                    "INCONCLUSIVE: tap executed successfully and the first bounded "
                    f"observation was unchanged; recovery re-observation was unavailable ({exc})."
                )
            else:
                recheck_attrs = dict(recheck_target.attrib) if recheck_target is not None else None
                if recheck_attrs is not None and before_attrs != recheck_attrs:
                    verification = (
                        "VERIFIED: tap executed successfully and a bounded recovery "
                        "re-observation detected a target UI attribute change."
                    )
                else:
                    verification = (
                        "INCONCLUSIVE: tap executed successfully, but the target UI node "
                        "remained unchanged after the bounded recovery re-observation; "
                        "the goal's visible effect could not be observed."
                    )
        else:
            verification = (
                "FAILED: tap did not execute successfully and the target UI node "
                "attributes were unchanged."
            )

        diagnosis = ""
        if verification.startswith(("INCONCLUSIVE", "FAILED")):
            from gemini_agent.tools import recover_android_mechanism
            diagnosis = "\n" + recover_android_mechanism(
                request=request,
                mechanism=candidate,
                verification=verification,
            )
        return (
            "Android UI mechanism execution:\n"
            f"Requested capability: {request.strip()}\n"
            f"Mechanism: {candidate}\n"
            "Validation: VIABLE\n"
            f"Resolved bounds: {bounds}\n"
            f"Tap result:\n{result}\n"
            f"Post-action verification: {verification}"
            f"{diagnosis}"
        )
    finally:
        try:
            run_root_command(f"rm -f {dump_path}")
        except (RuntimeError, ValueError):
            pass
