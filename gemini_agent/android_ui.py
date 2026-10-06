"""Bounded Android UI mechanism execution for Nova."""

import re
import xml.etree.ElementTree as ET

from gemini_agent.tools import run_root_command, validate_android_mechanism


def execute_validated_android_ui_mechanism(request: str, mechanism: str) -> str:
    """Execute one validated UI mechanism by resource ID using current UI bounds."""
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Request cannot be empty.")
    if not isinstance(mechanism, str) or not mechanism.strip():
        raise ValueError("Mechanism cannot be empty.")

    candidate = mechanism.strip()
    if ":" not in candidate:
        raise ValueError("Mechanism must use the bounded form: ui:<resource-id>.")

    kind, resource_id = candidate.split(":", 1)
    kind = kind.strip().lower()
    resource_id = resource_id.strip()
    if kind != "ui":
        raise ValueError(
            "This execution layer supports only validated ui:<resource-id> mechanisms."
        )
    if not resource_id:
        raise ValueError("UI resource ID cannot be empty.")

    validation = validate_android_mechanism(request, candidate)
    if "Status: VIABLE" not in validation:
        return (
            "Android UI mechanism execution blocked: the mechanism did not validate as viable.\n"
            + validation
        )

    dump_path = "/data/local/tmp/nova-ui-execution.xml"
    try:
        dump_result = run_root_command(f"uiautomator dump {dump_path}")
        if not dump_result.startswith("Exit code: 0"):
            return (
                "Android UI mechanism execution failed: UI hierarchy could not be captured.\n"
                f"{dump_result}"
            )

        xml_result = run_root_command(f"cat {dump_path}")
        xml_text = xml_result
        if "stdout:\n" in xml_text:
            xml_text = xml_text.split("stdout:\n", 1)[1]
            if "\nExit code:" in xml_text:
                xml_text = xml_text.split("\nExit code:", 1)[0]

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            return f"Android UI mechanism execution failed: invalid UI hierarchy: {exc}"

        target = None
        for node in root.iter("node"):
            if (
                node.attrib.get("resource-id") == resource_id
                and node.attrib.get("enabled") == "true"
            ):
                target = node
                break

        if target is None:
            return (
                "Android UI mechanism execution blocked: the validated control is no longer "
                "present as an enabled clickable control."
            )

        bounds = target.attrib.get("bounds", "")
        match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
        if not match:
            return (
                "Android UI mechanism execution blocked: the target control has no usable bounds."
            )

        left, top, right, bottom = map(int, match.groups())
        if right <= left or bottom <= top:
            return "Android UI mechanism execution blocked: target bounds are invalid."

        center_x = (left + right) // 2
        center_y = (top + bottom) // 2
        result = run_root_command(f"input tap {center_x} {center_y}")
        return (
            "Android UI mechanism execution:\n"
            f"Requested capability: {request.strip()}\n"
            f"Mechanism: {candidate}\n"
            "Validation: VIABLE\n"
            f"Resolved bounds: {bounds}\n"
            f"Tap result:\n{result}"
        )
    finally:
        try:
            run_root_command(f"rm -f {dump_path}")
        except (RuntimeError, ValueError):
            pass
