"""Offline tests for Nova's local tools."""

import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gemini_agent.tools import (
    RUN_COMMAND_DECLARATION,
    FIND_EXECUTABLE_DECLARATION,
    TOOL_DECLARATIONS,
    TOOL_HANDLERS,
    append_text_file,
    copy_file,
    copy_directory,
    calculator,
    self_test,
    send_android_keyevent,
    _run_bounded_root_action,
    _read_bounded_root_file,
    _dump_camera_ui_hierarchy,
    capability_inventory,
    discover_camera_control,
    discover_android_mechanisms,
    resolve_android_intent,
    inspect_android_ui,
    discover_android_ui_actions,
    validate_android_mechanism,
    execute_validated_android_mechanism,
    get_foreground_android_component,
    verify_android_component_presence,
    plan_capability_extension,
    apply_capability_extension,
    _load_persisted_capability_extensions,
    _persist_capability_extension,
    _normalize_android_mechanism_target,
    count_file_lines,
    create_directory,
    current_datetime,
    edit_text_file,
    get_file_info,
    get_file_access_time,
    get_file_modified_time,
    get_file_extension,
    get_file_name,
    get_file_stem,
    get_file_parent,
    get_file_permissions,
    get_system_info,
    get_system_battery_status,
    get_screen_state,
    get_screen_brightness,
    get_screen_timeout,
    get_screen_brightness_mode,
    get_screen_orientation,
    get_screen_resolution,
    get_screen_density,
    get_screen_refresh_rate,
    get_media_volume,
    get_hostname,
    get_network_addresses,
    get_network_interfaces,
    get_wifi_status,
    get_bluetooth_status,
    get_airplane_mode,
    get_load_average,
    get_system_memory_usage,
    get_system_cpu_usage,
    get_system_swap_usage,
    get_system_boot_time,
    get_system_uptime,
    get_process_id,
    get_current_working_directory,
    get_python_executable,
    get_cpu_count,
    get_memory_usage,
    get_temp_directory,
    get_home_directory,
    get_umask,
    get_process_uptime,
    get_process_thread_count,
    get_parent_process_id,
    get_process_group_id,
    get_session_id,
    get_user_id,
    path_exists,
    hash_file,
    get_directory_entry_count,
    get_disk_usage,
    get_directory_size,
    delete_directory,
    delete_file,
    find_files,
    move_file,
    move_directory,
    search_text,
    write_text_file,
    list_directory,
    list_directory_recursive,
    read_text_file,
    run_command,
    find_executable,
    diagnose_command_failure,
    verify_command_result,
    retry_command,
    recover_command,
    run_root_command,
    list_processes,
    get_process_status,
    get_process_command_line,
    get_process_executable,
    get_process_working_directory,
    get_process_parent_name,
    get_process_start_time,
    get_process_cpu_time,
    get_process_memory_usage,
    get_process_nice,
    send_android_intent,
)



class AndroidMechanismDiscoveryTests(unittest.TestCase):
    def test_discover_android_mechanisms_reports_candidates_without_action(self):
        with patch(
            "gemini_agent.tools.find_executable",
            side_effect=lambda name: f"Executable: /system/bin/{name}",
        ), patch(
            "gemini_agent.tools.run_root_command",
            return_value="Currently running services:\ncamera\naudio\nwindow",
        ):
            result = discover_android_mechanisms("control the camera")
        self.assertIn("Android mechanism discovery (read-only):", result)
        self.assertIn("dumpsys: Executable: /system/bin/dumpsys", result)
        self.assertIn("Candidate Android services:", result)
        self.assertIn("camera", result)
        self.assertIn("No action was performed", result)

    def test_discover_android_mechanisms_rejects_empty_request(self):
        with self.assertRaises(ValueError):
            discover_android_mechanisms("")



class CapabilityInventoryToolTests(unittest.TestCase):
    def test_capability_inventory_lists_registered_tools(self):
        result = capability_inventory()
        self.assertRegex(result, r"^Capabilities \(\d+\):")
        self.assertIn("- calculator: Calculate basic arithmetic expressions.", result)
        self.assertIn("- self_test: Run a small deterministic health check", result)

    def test_capability_inventory_is_registered(self):
        self.assertIs(TOOL_HANDLERS["capability_inventory"], capability_inventory)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("capability_inventory", names)


class AndroidActionToolTests(unittest.TestCase):
    def test_send_android_intent_validates_and_uses_root_shell(self):
        with patch("gemini_agent.tools._run_bounded_root_action", return_value="Exit code: 0") as root:
            result = send_android_intent("IMAGE_CAPTURE")
        self.assertIn("Android intent android.media.action.IMAGE_CAPTURE started.", result)
        root.assert_called_once_with("am start -a android.media.action.IMAGE_CAPTURE")

    def test_send_android_intent_rejects_unsupported_action(self):
        with self.assertRaisesRegex(ValueError, "Unsupported Android intent action"):
            send_android_intent("android.intent.action.DELETE")

    def test_send_android_intent_is_registered(self):
        self.assertIs(TOOL_HANDLERS["send_android_intent"], send_android_intent)
        self.assertIn("send_android_intent", [d["name"] for d in TOOL_DECLARATIONS])

    def test_send_android_keyevent_validates_and_uses_root_shell(self):
        completed = type("Completed", (), {"stdout": "", "stderr": "", "returncode": 0})()
        with patch("gemini_agent.tools._run_bounded_root_action", return_value="Exit code: 0") as root:
            result = send_android_keyevent("CAMERA")
        self.assertIn("Android key event 27 sent.", result)
        root.assert_called_once_with("input keyevent 27")

    def test_send_android_keyevent_supports_volume_down(self):
        with patch("gemini_agent.tools._run_bounded_root_action", return_value="Exit code: 0\\nstdout:") as root:
            result = send_android_keyevent("VOLUME_DOWN")
        self.assertIn("Android key event 25 sent.", result)
        root.assert_called_once_with("input keyevent 25")

    def test_send_android_keyevent_rejects_unsupported_key(self):
        with self.assertRaisesRegex(ValueError, "Unsupported Android keycode"):
            send_android_keyevent("POWER")

    def test_send_android_keyevent_is_registered(self):
        self.assertIs(TOOL_HANDLERS["send_android_keyevent"], send_android_keyevent)
        self.assertIn("send_android_keyevent", [d["name"] for d in TOOL_DECLARATIONS])


class CapabilityExtensionToolTests(unittest.TestCase):
    def _source(self):
        return (
            "TOOL_DECLARATIONS = [\n"
            "    {\n"
            '        \"name\": \"old_tool\",\n'
            '        \"description\": \"old\",\n'
            '        "parameters": {"type": "OBJECT", "properties": {}},\n'
            "    },\n"
            "]\n"
            "TOOL_HANDLERS: dict[str, Callable[..., str]] = {\n"
            '    \"old_tool\": lambda: \"ok\",\n'
            "}\n\n"
            "def self_test():\n"
            '    return \"ok\"\n'
        )

    def test_still_image_camera_foreground_action_is_allowlisted(self):
        with patch("gemini_agent.tools.subprocess.run") as run:
            run.return_value.stdout = ""
            run.return_value.stderr = ""
            run.return_value.returncode = 0
            result = _run_bounded_root_action("am start -a android.media.action.STILL_IMAGE_CAMERA")
        self.assertIn("Exit code: 0", result)
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["su"])
        self.assertEqual(run.call_args.kwargs["input"], "am start -a android.media.action.STILL_IMAGE_CAMERA\nexit\n")

    def test_dump_camera_ui_hierarchy_uses_bounded_temp_file(self):
        completed_dump = type("Completed", (), {"stdout": "", "stderr": "", "returncode": 0})()
        completed_read = type(
            "Completed",
            (),
            {"stdout": "<hierarchy><node text=\"Shutter\" content-desc=\"Shutter\" /></hierarchy>", "stderr": "", "returncode": 0},
        )()
        with patch("gemini_agent.tools.subprocess.run", side_effect=[completed_dump, completed_read, completed_dump]) as run:
            result = _dump_camera_ui_hierarchy()
        self.assertIn("Shutter", result)
        self.assertEqual(run.call_count, 3)
        self.assertEqual(run.call_args_list[0].kwargs["input"], "uiautomator dump /data/local/tmp/nova_camera_ui.xml\n")
        self.assertEqual(run.call_args_list[1].kwargs["input"], "cat /data/local/tmp/nova_camera_ui.xml\n")
        self.assertEqual(run.call_args_list[2].kwargs["input"], "rm -f /data/local/tmp/nova_camera_ui.xml\n")

    def test_resolve_android_intent_is_read_only_and_allowlisted(self):
        with patch("gemini_agent.tools.run_root_command", return_value="Exit code: 0\nstdout:\ncom.transsion.camera/.app.CaptureActivity"):
            result = resolve_android_intent("IMAGE_CAPTURE")
        self.assertIn("android.media.action.IMAGE_CAPTURE", result)
        self.assertIn("com.transsion.camera/.app.CaptureActivity", result)
        self.assertIn("not launched", result)

    def test_get_foreground_android_component_is_read_only_and_registered(self):
        with patch(
            "gemini_agent.tools.run_root_command",
            return_value="Exit code: 0\nstdout:\n  topResumedActivity=ActivityRecord{u0 com.termux/.app.TermuxActivity}",
        ) as root:
            result = get_foreground_android_component()
        root.assert_called_once_with("dumpsys activity activities")
        self.assertIn("com.termux/.app.TermuxActivity", result)
        self.assertIn("read-only", result)
        self.assertIn("No interaction", result)
        self.assertIs(
            TOOL_HANDLERS["get_foreground_android_component"],
            get_foreground_android_component,
        )
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_foreground_android_component", names)

    def test_discover_android_ui_actions_reports_clickable_controls_without_interaction(self):
        xml = (
            "Exit code: 0\nstdout:\n"
            "<hierarchy><node text=\"Camera\"><node text=\"Capture\" "
            "resource-id=\"com.transsion.camera:id/shutter_button\" "
            "class=\"android.widget.ImageView\" clickable=\"true\" enabled=\"true\" "
            "bounds=\"[294,1316][426,1448]\" /></node></hierarchy>"
        )
        with patch(
            "gemini_agent.tools.run_root_command",
            side_effect=["Exit code: 0", "Exit code: 0"],
        ) as root, patch(
            "gemini_agent.tools._read_bounded_root_file",
            return_value=xml.split("stdout:\n", 1)[1],
        ) as bounded_read:
            result = discover_android_ui_actions()
        self.assertIn("Clickable enabled controls found: 1", result)
        self.assertIn("shutter_button", result)
        self.assertIn("Capture", result)
        self.assertIn("no interaction or device state change", result)
        self.assertEqual(root.call_args_list[0].args[0], "uiautomator dump /data/local/tmp/nova-ui-actions.xml")
        bounded_read.assert_called_once_with("/data/local/tmp/nova-ui-actions.xml", 64 * 1024)
        self.assertEqual(root.call_args_list[1].args[0], "rm -f /data/local/tmp/nova-ui-actions.xml")
        self.assertIs(TOOL_HANDLERS["discover_android_ui_actions"], discover_android_ui_actions)
        self.assertIn("discover_android_ui_actions", [d["name"] for d in TOOL_DECLARATIONS])

    def test_validate_android_mechanism_validates_without_executing_capability(self):
        with patch(
            "gemini_agent.tools.resolve_android_intent",
            return_value=(
                "Android intent resolution (read-only): android.media.action.IMAGE_CAPTURE\n"
                "Exit code: 0\nstdout:\ncom.transsion.camera/.app.CaptureActivity"
            ),
        ) as resolver:
            result = validate_android_mechanism(
                "capture a photo",
                "intent:android.media.action.IMAGE_CAPTURE",
            )
        self.assertIn("Status: VIABLE", result)
        self.assertIn("CaptureActivity", result)
        self.assertIn("No capability action was executed", result)
        resolver.assert_called_once_with("android.media.action.IMAGE_CAPTURE")
        self.assertIs(TOOL_HANDLERS["validate_android_mechanism"], validate_android_mechanism)
        self.assertIn("validate_android_mechanism", [d["name"] for d in TOOL_DECLARATIONS])

    def test_inspect_android_ui_captures_hierarchy_and_cleans_up(self):
        xml = '<hierarchy rotation="0"><node text="Camera" /></hierarchy>'
        with patch(
            "gemini_agent.tools.run_root_command",
            side_effect=["Exit code: 0", "Exit code: 0"],
        ) as root, patch(
            "gemini_agent.tools._read_bounded_root_file",
            return_value=xml,
        ) as bounded_read:
            result = inspect_android_ui()
        self.assertEqual(
            root.call_args_list[0].args[0],
            "uiautomator dump /data/local/tmp/nova-ui-hierarchy.xml",
        )
        bounded_read.assert_called_once_with("/data/local/tmp/nova-ui-hierarchy.xml", 64 * 1024)
        self.assertEqual(
            root.call_args_list[1].args[0],
            "rm -f /data/local/tmp/nova-ui-hierarchy.xml",
        )
        self.assertIn('text="Camera"', result)
        self.assertIn("without interaction", result)
        self.assertIs(TOOL_HANDLERS["inspect_android_ui"], inspect_android_ui)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("inspect_android_ui", names)

    def test_bounded_read_allows_ui_hierarchy_path(self):
        completed = type("Completed", (), {"returncode": 0, "stdout": b"<hierarchy />", "stderr": b""})()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed) as run:
            result = _read_bounded_root_file("/data/local/tmp/nova-ui-hierarchy.xml", 64 * 1024)
        self.assertEqual(result, "<hierarchy />")
        run.assert_called_once()

    def test_inspect_android_ui_filters_to_one_enabled_selector(self):
        xml = (
            '<hierarchy>'
            '<node text="ESC" enabled="true" clickable="true" focused="false" '
            'selected="false" bounds="[6,812][107,887]" />'
            '<node text="CTRL" enabled="true" clickable="true" focused="false" '
            'selected="true" checked="false" bounds="[107,887][208,962]" />'
            '</hierarchy>'
        )
        with patch(
            "gemini_agent.tools.run_root_command",
            side_effect=["Exit code: 0", "Exit code: 0"],
        ) as root, patch(
            "gemini_agent.tools._read_bounded_root_file",
            return_value=xml,
        ) as bounded_read:
            result = inspect_android_ui("ui-text:CTRL")
        self.assertIn("Matched selector: ui-text:CTRL", result)
        self.assertIn("text='CTRL'", result)
        self.assertIn("selected='true'", result)
        self.assertNotIn("text='ESC'", result)
        bounded_read.assert_called_once_with("/data/local/tmp/nova-ui-hierarchy.xml", 64 * 1024)
        self.assertEqual(
            root.call_args_list[1].args[0],
            "rm -f /data/local/tmp/nova-ui-hierarchy.xml",
        )

    def test_resolve_android_intent_rejects_unknown_action(self):
        with self.assertRaises(ValueError):
            resolve_android_intent("android.intent.action.UNKNOWN")

    def test_discover_camera_control_is_read_only_and_registered(self):
        with patch("gemini_agent.tools.find_executable", side_effect=lambda name: f"Executable: /system/bin/{name}"):
            with patch(
                "gemini_agent.tools.run_root_command",
                return_value="Currently running services:\ncamera\naudio\nwindow",
            ):
                with patch("gemini_agent.tools._run_bounded_root_action") as action:
                    with patch("gemini_agent.tools._dump_camera_ui_hierarchy") as hierarchy:
                        result = discover_camera_control()
        self.assertIn("Android mechanism discovery (read-only):", result)
        self.assertIn("Candidate Android services:", result)
        self.assertIn("camera", result)
        self.assertIn("No action was performed", result)
        action.assert_not_called()
        hierarchy.assert_not_called()
        self.assertIs(TOOL_HANDLERS["discover_camera_control"], discover_camera_control)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("discover_camera_control", names)


    def test_plan_capability_extension_for_camera_is_plan_only(self):
        result = plan_capability_extension("control the phone's camera shutter")
        self.assertIn("Extension plan: capability is missing.", result)
        self.assertIn("Proposed tool: extend_camera_shutter", result)

    def test_apply_capability_extension_blocks_unsupported_camera(self):
        result = apply_capability_extension(
            "control the phone's camera shutter",
            "gemini_agent/tools.py",
            "existing_tool",
            "discover_camera_control",
            "{}",
            "Take a photo with the phone camera.",
        )
        self.assertIn("Extension blocked:", result)
        self.assertIn("inspection or orchestration tool", result)

    def test_android_mechanism_extension_uses_actual_handler_anchor(self):
        source = Path("gemini_agent/tools.py").read_text(encoding="utf-8")
        updated = source
        handler_marker = "TOOL_HANDLERS: dict[str, Callable[..., str]] = {"
        function_source = "def generated_probe():\n    return _run_android_mechanism_extension('open camera', 'intent:android.media.action.IMAGE_CAPTURE')"
        handler_insert_index = updated.rfind(handler_marker)
        self.assertGreater(handler_insert_index, updated.find("handler_marker ="))
        updated = (
            updated[:handler_insert_index]
            + "\n"
            + function_source
            + "\n"
            + updated[handler_insert_index:]
        )
        compile(updated, "generated_tools.py", "exec")

    def test_android_mechanism_extension_normalizes_embedded_model_formatting(self):
        self.assertEqual(
            _normalize_android_mechanism_target(
                "validated candidate: intent: android.media.action.IMAGE_CAPTURE"
            ),
            "intent:android.media.action.IMAGE_CAPTURE",
        )

    def test_apply_capability_extension_structured_transaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "gemini_agent" / "tools.py"
            target.parent.mkdir()
            target.write_text(self._source(), encoding="utf-8")
            completed = type("Completed", (), {"returncode": 0, "stdout": "OK"})()
            with patch("gemini_agent.tools._filesystem_root", return_value=root):
                with patch("gemini_agent.tools.subprocess.run", return_value=completed):
                    result = apply_capability_extension(
                        "combine two existing local operations",
                        "gemini_agent/tools.py",
                        "existing_tool",
                        "calculator",
                        '{"expression": "2 + 2"}',
                        "Combine the existing operations.",
                    )
            self.assertIn("Extension status: source edit applied and transaction committed.", result)
            updated = target.read_text(encoding="utf-8")
            self.assertIn("def combine_two_existing_local_operations()", updated)
            self.assertIn('"name": "combine_two_existing_local_operations"', updated)
            self.assertIn('"combine_two_existing_local_operations": combine_two_existing_local_operations', updated)

            namespace = {}
            exec(compile(updated, str(target), "exec"), namespace)
            self.assertIn("combine_two_existing_local_operations", namespace["TOOL_HANDLERS"])
            self.assertIs(namespace["TOOL_HANDLERS"]["combine_two_existing_local_operations"], namespace["combine_two_existing_local_operations"])

    def test_android_mechanism_discovery_reports_resolved_intent_candidates(self):
        with patch(
            "gemini_agent.tools.resolve_android_intent",
            return_value="Android intent resolution (read-only):\nIntent was resolved only; it was not launched and no device state was modified.",
        ):
            result = discover_android_mechanisms("open the device camera")
        self.assertIn("Discovered bounded intent mechanisms:", result)
        self.assertIn("intent:android.media.action.IMAGE_CAPTURE", result)
        self.assertIn("intent:android.media.action.STILL_IMAGE_CAMERA", result)

    def test_android_mechanism_extension_accepts_whitespace_after_prefix(self):
        self.assertEqual(
            _normalize_android_mechanism_target("intent: android.media.action.IMAGE_CAPTURE"),
            "intent:android.media.action.IMAGE_CAPTURE",
        )
    def test_persisted_android_capability_survives_source_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "capabilities.json"
            name = "persisted_android_test_capability"
            with patch.dict(
                os.environ,
                {"NOVA_CAPABILITY_STORE": str(store)},
                clear=False,
            ):
                _persist_capability_extension(
                    name,
                    "Persisted Android test capability.",
                    "android_mechanism",
                    "intent:android.media.action.IMAGE_CAPTURE",
                    "{}",
                    "open the camera",
                )
                TOOL_HANDLERS.pop(name, None)
                TOOL_DECLARATIONS[:] = [
                    item for item in TOOL_DECLARATIONS
                    if item.get("name") != name
                ]
                _load_persisted_capability_extensions()

            self.assertIn(name, TOOL_HANDLERS)
            self.assertIn(name, [item["name"] for item in TOOL_DECLARATIONS])
            self.assertIn(
                "_run_android_mechanism_extension",
                TOOL_HANDLERS[name].__code__.co_names,
            )
            store.unlink()

    def test_apply_capability_extension_can_persist_validated_android_mechanism(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "gemini_agent" / "tools.py"
            target.parent.mkdir()
            target.write_text(self._source(), encoding="utf-8")
            with patch("gemini_agent.tools._filesystem_root", return_value=root), \
                 patch.dict(
                     os.environ,
                     {"NOVA_CAPABILITY_STORE": str(root / "capabilities.json")},
                     clear=False,
                 ), \
                 patch(
                     "gemini_agent.tools.validate_android_mechanism",
                     return_value="Android mechanism validation (read-only):\\nStatus: VIABLE",
                 ), \
                 patch("gemini_agent.tools.subprocess.run") as run:
                run.return_value = type("Completed", (), {"returncode": 0, "stdout": "OK", "stderr": ""})()
                result = apply_capability_extension(
                    "open the device camera",
                    "gemini_agent/tools.py",
                    "android_mechanism",
                    "intent:android.media.action.IMAGE_CAPTURE",
                    "{}",
                    "Open the device camera using the validated Android mechanism.",
                )
            self.assertIn("Extension status: source edit applied and transaction committed.", result)
            updated = target.read_text(encoding="utf-8")
            self.assertIn("_run_android_mechanism_extension", updated)
            self.assertIn("intent:android.media.action.IMAGE_CAPTURE", updated)
            self.assertIn('"name": "camera_shutter"', updated)
            self.assertIn('"camera_shutter": camera_shutter', updated)

    def test_apply_capability_extension_blocks_nonviable_android_mechanism(self):
        with patch(
            "gemini_agent.tools.validate_android_mechanism",
            return_value="Android mechanism validation (read-only):\\nStatus: NOT VIABLE",
        ):
            result = apply_capability_extension(
                "open the camera",
                "gemini_agent/tools.py",
                "android_mechanism",
                "intent:android.media.action.IMAGE_CAPTURE",
                "{}",
                "Open the device camera using the validated Android mechanism.",
            )
        self.assertIn("discovered Android mechanism is not viable", result)

    def test_apply_capability_extension_rolls_back_when_tests_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "gemini_agent" / "tools.py"
            target.parent.mkdir()
            original = self._source()
            target.write_text(original, encoding="utf-8")
            completed = type("Completed", (), {"returncode": 1, "stdout": "FAILED"})()
            with patch("gemini_agent.tools._filesystem_root", return_value=root):
                with patch("gemini_agent.tools.subprocess.run", return_value=completed):
                    result = apply_capability_extension(
                        "combine two existing local operations",
                        "gemini_agent/tools.py",
                        "existing_tool",
                        "calculator",
                        '{"expression": "2 + 2"}',
                        "Combine the existing operations.",
                    )
            self.assertIn("Extension rolled back:", result)
            self.assertEqual(target.read_text(encoding="utf-8"), original)

    def test_apply_capability_extension_rejects_invalid_function(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "gemini_agent" / "tools.py"
            target.parent.mkdir()
            target.write_text(self._source(), encoding="utf-8")
            with patch("gemini_agent.tools._filesystem_root", return_value=root):
                result = apply_capability_extension(
                    "combine two existing local operations",
                    "gemini_agent/tools.py",
                    "invalid_kind",
                    "calculator",
                    '{"expression": "2 + 2"}',
                    "Combine the existing operations.",
                )
            self.assertIn("implementation_kind must be 'existing_tool' or 'android_mechanism'", result)

    def test_apply_capability_extension_rejects_invalid_primitive_arguments(self):
        result = apply_capability_extension(
            "combine two existing local operations",
            "gemini_agent/tools.py",
            "existing_tool",
            "calculator",
            "{}",
            "Combine the existing operations.",
        )
        self.assertIn("arguments do not match existing primitive 'calculator'", result)

    def test_apply_capability_extension_rejects_wrong_function_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "gemini_agent" / "tools.py"
            target.parent.mkdir()
            target.write_text(self._source(), encoding="utf-8")
            with patch("gemini_agent.tools._filesystem_root", return_value=root):
                result = apply_capability_extension(
                    "combine two existing local operations",
                    "gemini_agent/tools.py",
                    "existing_tool",
                    "not_a_real_tool",
                    "{}",
                    "Combine the existing operations.",
                )
            self.assertIn("is not available", result)

    def test_apply_capability_extension_rejects_missing_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "gemini_agent" / "tools.py"
            target.parent.mkdir()
            target.write_text(self._source(), encoding="utf-8")
            with patch("gemini_agent.tools._filesystem_root", return_value=root):
                with self.assertRaises(ValueError):
                    apply_capability_extension(
                        "combine two existing local operations",
                        "gemini_agent/capabilities/camera_shutter.py",
                        "existing_tool",
                        "calculator",
                        '{"expression": "2 + 2"}',
                        "Combine the existing operations.",
                    )

    def test_apply_capability_extension_rejects_existing_capability(self):
        result = apply_capability_extension(
            "what is the battery level",
            "gemini_agent/tools.py",
            "existing_tool",
            "calculator",
            '{"expression": "2 + 2"}',
            "Combine the existing operations.",
        )
        self.assertIn("Extension not applied:", result)

class SelfTestToolTests(unittest.TestCase):
    def test_capability_gap_reports_match(self):
        from gemini_agent.tools import assess_capability_gap
        result = assess_capability_gap("what is the battery level")
        self.assertIn("get_system_battery_status", result)
        self.assertIn("Capability match:", result)

    def test_capability_gap_reports_missing_capability(self):
        from gemini_agent.tools import assess_capability_gap
        result = assess_capability_gap("control the phone's camera shutter")
        self.assertIn("Capability gap:", result)

    def test_capability_extension_plan_for_missing_capability(self):
        result = plan_capability_extension("control the phone's camera shutter")
        self.assertIn("Extension plan: capability is missing.", result)
        self.assertIn("Proposed tool: extend_camera_shutter", result)
        self.assertIn("Status: plan only; no code or device state was modified.", result)

    def test_apply_capability_extension_blocks_inspection_primitive(self):
        result = apply_capability_extension(
            "control the phone camera shutter",
            "gemini_agent/tools.py",
            "existing_tool",
            "discover_camera_control",
            "{}",
            "Take a photo with the phone camera.",
        )
        self.assertIn("Extension blocked:", result)
        self.assertIn("inspection or orchestration tool", result)

    def test_capability_extension_plan_ignores_model_generated_camera_filler(self):
        result = plan_capability_extension(
            "add a capability to open the device camera and capture a photo"
        )
        self.assertIn("Proposed tool: extend_camera_shutter", result)
        self.assertNotIn("extend_add_open_device_camera_and", result)

    def test_capability_extension_plan_is_registered(self):
        self.assertIs(TOOL_HANDLERS["plan_capability_extension"], plan_capability_extension)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("plan_capability_extension", names)

    def test_self_test_passes(self):
        result = self_test()
        self.assertRegex(result, r"^Self-test: PASS \(5/5 checks passed\)$")

    def test_self_test_is_registered(self):
        self.assertIs(TOOL_HANDLERS["self_test"], self_test)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("self_test", names)


class ReplanAndroidMechanismTests(unittest.TestCase):
    def test_replan_android_mechanism_selects_untried_viable_alternative(self):
        from gemini_agent.tools import replan_android_mechanism
        with patch("gemini_agent.tools.discover_android_mechanisms", return_value=(
            "Android mechanism discovery (read-only):\n"
            "Discovered bounded intent mechanisms:\n"
            "intent:android.media.action.FIRST\n"
            "intent:android.media.action.SECOND"
        )), patch("gemini_agent.tools.validate_android_mechanism", return_value=(
            "Android mechanism validation (read-only):\nStatus: VIABLE\n"
            "Evidence:\ncom.example/.SecondActivity"
        )), patch("gemini_agent.tools.send_android_intent", return_value="Android intent started."), patch(
            "gemini_agent.tools.get_foreground_android_component",
            return_value="topResumedActivity=com.example/.SecondActivity",
        ):
            result = replan_android_mechanism(
                "open something", "intent:android.media.action.FIRST"
            )
        self.assertIn("selected alternate viable mechanism", result)
        self.assertIn("intent:android.media.action.SECOND", result)
        self.assertIn("VERIFIED", result)

    def test_execute_android_mechanism_dispatches_ui_mechanism(self):
        from gemini_agent.tools import execute_android_mechanism
        with patch(
            "gemini_agent.android_ui.execute_validated_android_ui_mechanism",
            return_value="UI EXECUTED",
        ) as execute_ui:
            result = execute_android_mechanism("press CTRL", "ui-text:CTRL")
        self.assertEqual(result, "UI EXECUTED")
        execute_ui.assert_called_once_with(request="press CTRL", mechanism="ui-text:CTRL")

    def test_execute_android_mechanism_blocks_unsupported_mechanism_type(self):
        from gemini_agent.tools import execute_android_mechanism
        result = execute_android_mechanism("use service", "service:camera")
        self.assertIn("no bounded executor exists", result)

    def test_replan_android_mechanism_stops_when_no_alternative_exists(self):
        from gemini_agent.tools import replan_android_mechanism
        with patch("gemini_agent.tools.discover_android_mechanisms", return_value=(
            "Discovered bounded intent mechanisms:\n"
            "intent:android.media.action.FIRST"
        )):
            result = replan_android_mechanism(
                "open something", "intent:android.media.action.FIRST"
            )
        self.assertIn("no untried viable alternative", result)
        self.assertIn("Outcome: FAILED", result)


class FindExecutableToolTests(unittest.TestCase):
    def test_find_executable_uses_path(self):
        with patch("gemini_agent.tools.shutil.which", return_value="/system/bin/dumpsys"):
            result = find_executable("dumpsys")
        self.assertEqual(result, "Executable: /system/bin/dumpsys")

    def test_find_executable_reports_missing(self):
        with patch("gemini_agent.tools.shutil.which", return_value=None):
            with patch("gemini_agent.tools.os.path.isfile", return_value=False):
                result = find_executable("definitely_missing")
        self.assertEqual(result, "Executable not found: definitely_missing")

    def test_find_executable_is_registered(self):
        self.assertIs(TOOL_HANDLERS["find_executable"], find_executable)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("find_executable", names)
        self.assertEqual(FIND_EXECUTABLE_DECLARATION["name"], "find_executable")


class DiagnoseCommandFailureToolTests(unittest.TestCase):
    def test_diagnoses_missing_executable(self):
        result = diagnose_command_failure("dumpsys", "dumpsys: command not found")
        self.assertIn("executable or path not found", result)
        self.assertIn("find_executable", result)

    def test_diagnoses_permission_failure(self):
        result = diagnose_command_failure("dumpsys", "Permission denied")
        self.assertIn("permission denied", result)
        self.assertIn("manual su workflow", result)

    def test_diagnoses_android_service_failure(self):
        result = diagnose_command_failure("settings get global airplane_mode_on", "Failed transaction")
        self.assertIn("Android service or IPC failure", result)
        self.assertIn("run_root_command", result)

    def test_diagnose_command_failure_is_registered(self):
        self.assertIs(TOOL_HANDLERS["diagnose_command_failure"], diagnose_command_failure)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("diagnose_command_failure", names)

class RunRootCommandToolTests(unittest.TestCase):
    def test_run_root_command_uses_manual_su_shell(self):
        completed = type("Completed", (), {"stdout": "/system/bin/dumpsys\n", "stderr": "", "returncode": 0})()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed) as run:
            result = run_root_command("command -v dumpsys")
            bare_result = run_root_command("dumpsys")
        self.assertEqual(result, "Exit code: 0\nstdout:\n/system/bin/dumpsys")
        self.assertEqual(bare_result, "Exit code: 0\nstdout:\n/system/bin/dumpsys")
        self.assertEqual(run.call_args.args[0], ["su"])
        self.assertEqual(run.call_args.kwargs["input"], "dumpsys\n")

    def test_run_root_command_rejects_non_diagnostic_commands(self):
        with self.assertRaises(ValueError):
            run_root_command("rm -rf /")

    def test_run_root_command_is_registered(self):
        self.assertIs(TOOL_HANDLERS["run_root_command"], run_root_command)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("run_root_command", names)


class ListProcessesToolTests(unittest.TestCase):
    def test_list_processes_returns_pid_and_name(self):
        result = list_processes()
        self.assertTrue(result)
        self.assertTrue(all(line.split(maxsplit=1)[0].isdigit() for line in result.splitlines()))

    def test_list_processes_is_registered(self):
        self.assertIs(TOOL_HANDLERS["list_processes"], list_processes)
        self.assertNotEqual(TOOL_DECLARATIONS[-1]["name"], "list_processes")


class GetProcessStatusToolTests(unittest.TestCase):
    def test_get_process_status_returns_basic_status(self):
        result = get_process_status(str(os.getpid()))
        self.assertIn(f"PID: {os.getpid()}", result)
        self.assertIn("Name:", result)
        self.assertIn("State:", result)

    def test_get_process_status_rejects_invalid_pid(self):
        with self.assertRaisesRegex(ValueError, "PID"):
            get_process_status("not-a-pid")

    def test_get_process_status_rejects_missing_process(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            get_process_status("999999999")

    def test_get_process_status_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_process_status"], get_process_status)

class GetProcessExecutableToolTests(unittest.TestCase):
    def test_get_process_executable_returns_path(self):
        result = get_process_executable(str(os.getpid()))
        self.assertTrue(result)
        self.assertIn("python", result.lower())

    def test_get_process_executable_rejects_invalid_pid(self):
        with self.assertRaisesRegex(ValueError, "PID"):
            get_process_executable("not-a-pid")

    def test_get_process_executable_rejects_missing_process(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            get_process_executable("999999999")

    def test_get_process_executable_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_process_executable"], get_process_executable)


class GetProcessWorkingDirectoryToolTests(unittest.TestCase):
    def test_get_process_working_directory_returns_path(self):
        result = get_process_working_directory(str(os.getpid()))
        self.assertTrue(result)
        self.assertEqual(result, os.getcwd())

    def test_get_process_working_directory_rejects_invalid_pid(self):
        with self.assertRaisesRegex(ValueError, "PID"):
            get_process_working_directory("not-a-pid")

    def test_get_process_working_directory_rejects_missing_process(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            get_process_working_directory("999999999")

    def test_get_process_working_directory_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_process_working_directory"], get_process_working_directory)


class GetProcessParentNameToolTests(unittest.TestCase):
    def test_get_process_parent_name_returns_name(self):
        result = get_process_parent_name(str(os.getpid()))
        self.assertTrue(result)

    def test_get_process_parent_name_rejects_invalid_pid(self):
        with self.assertRaisesRegex(ValueError, "PID"):
            get_process_parent_name("not-a-pid")

    def test_get_process_parent_name_rejects_missing_process(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            get_process_parent_name("999999999")

    def test_get_process_parent_name_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_process_parent_name"], get_process_parent_name)


class GetProcessStartTimeToolTests(unittest.TestCase):
    def test_get_process_start_time_returns_iso_time(self):
        result = get_process_start_time(str(os.getpid()))
        self.assertRegex(result, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")

    def test_get_process_start_time_rejects_invalid_pid(self):
        with self.assertRaisesRegex(ValueError, "PID"):
            get_process_start_time("not-a-pid")

    def test_get_process_start_time_rejects_missing_process(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            get_process_start_time("999999999")

    def test_get_process_start_time_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_process_start_time"], get_process_start_time)




class GetProcessCpuTimeToolTests(unittest.TestCase):
    def test_get_process_cpu_time_returns_components(self):
        result = get_process_cpu_time(str(os.getpid()))
        self.assertRegex(result, r"^User: \d+\.\d{3} seconds\nSystem: \d+\.\d{3} seconds\nTotal: \d+\.\d{3} seconds$")

    def test_get_process_cpu_time_rejects_invalid_pid(self):
        with self.assertRaisesRegex(ValueError, "PID"):
            get_process_cpu_time("not-a-pid")

    def test_get_process_cpu_time_rejects_missing_process(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            get_process_cpu_time("999999999")

    def test_get_process_cpu_time_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_process_cpu_time"], get_process_cpu_time)


class GetProcessMemoryUsageToolTests(unittest.TestCase):
    def test_get_process_memory_usage_returns_positive_bytes(self):
        result = get_process_memory_usage(str(os.getpid()))
        self.assertGreater(int(result), 0)

    def test_get_process_memory_usage_rejects_invalid_pid(self):
        with self.assertRaisesRegex(ValueError, "PID"):
            get_process_memory_usage("not-a-pid")

    def test_get_process_memory_usage_rejects_missing_process(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            get_process_memory_usage("999999999")

    def test_get_process_memory_usage_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_process_memory_usage"], get_process_memory_usage)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_process_memory_usage", names)


class GetNetworkAddressesToolTests(unittest.TestCase):
    def test_get_network_addresses_returns_nonempty_value(self):
        result = get_network_addresses()
        self.assertTrue(result)

    def test_get_network_addresses_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_network_addresses"], get_network_addresses)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_network_addresses", names)


class GetWifiStatusToolTests(unittest.TestCase):
    def test_get_wifi_status_parses_enabled_state(self):
        completed = type("Completed", (), {"stdout": "Wi-Fi is enabled\n", "stderr": ""})()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed) as run:
            result = get_wifi_status()
        self.assertEqual(result, "Wi-Fi: Enabled")
        self.assertEqual(run.call_args.args[0], ["su"])
        self.assertEqual(run.call_args.kwargs["input"], "/system/bin/cmd wifi status\n")

    def test_get_wifi_status_parses_disabled_state(self):
        completed = type("Completed", (), {"stdout": "Wi-Fi is disabled\n", "stderr": ""})()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed):
            self.assertEqual(get_wifi_status(), "Wi-Fi: Disabled")

    def test_get_wifi_status_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_wifi_status"], get_wifi_status)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_wifi_status", names)


class GetBluetoothStatusToolTests(unittest.TestCase):
    def test_get_bluetooth_status_parses_enabled_state(self):
        completed = type("Completed", (), {"stdout": "1\\n", "stderr": ""})()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed) as run:
            result = get_bluetooth_status()
        self.assertEqual(result, "Bluetooth: Enabled")
        self.assertEqual(run.call_args.args[0], ["su", "-c", "/system/bin/settings get global bluetooth_on"])

    def test_get_bluetooth_status_parses_disabled_state(self):
        completed = type("Completed", (), {"stdout": "0\\n", "stderr": ""})()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed):
            self.assertEqual(get_bluetooth_status(), "Bluetooth: Disabled")

    def test_get_bluetooth_status_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_bluetooth_status"], get_bluetooth_status)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_bluetooth_status", names)




class GetAirplaneModeToolTests(unittest.TestCase):
    def test_get_airplane_mode_parses_enabled_state(self):
        completed = type("Completed", (), {"stdout": "1\n", "stderr": ""})()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed) as run:
            result = get_airplane_mode()
        self.assertEqual(result, "Airplane mode: Enabled")
        self.assertEqual(run.call_args.args[0], ["su"])
        self.assertEqual(run.call_args.kwargs["input"], "/system/bin/settings get global airplane_mode_on\n")

    def test_get_airplane_mode_parses_disabled_state(self):
        completed = type("Completed", (), {"stdout": "0\n", "stderr": ""})()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed):
            self.assertEqual(get_airplane_mode(), "Airplane mode: Disabled")

    def test_get_airplane_mode_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_airplane_mode"], get_airplane_mode)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_airplane_mode", names)


class GetNetworkInterfacesToolTests(unittest.TestCase):
    def test_get_network_interfaces_returns_nonempty_value(self):
        result = get_network_interfaces()
        self.assertTrue(result)
        self.assertIn(":", result)

    def test_get_network_interfaces_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_network_interfaces"], get_network_interfaces)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_network_interfaces", names)


class GetLoadAverageToolTests(unittest.TestCase):
    def test_get_load_average_returns_three_values(self):
        result = get_load_average()
        self.assertRegex(result, r"^1m: -?\d+\.\d{2}\n5m: -?\d+\.\d{2}\n15m: -?\d+\.\d{2}$")

    def test_get_load_average_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_load_average"], get_load_average)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_load_average", names)


class GetProcessNiceToolTests(unittest.TestCase):
    def test_get_process_nice_returns_integer(self):
        result = get_process_nice(str(os.getpid()))
        self.assertRegex(result, r"^-?\d+$")

    def test_get_process_nice_rejects_invalid_pid(self):
        with self.assertRaisesRegex(ValueError, "PID"):
            get_process_nice("not-a-pid")

    def test_get_process_nice_rejects_missing_process(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            get_process_nice("999999999")

    def test_get_process_nice_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_process_nice"], get_process_nice)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_process_nice", names)


class GetProcessCommandLineToolTests(unittest.TestCase):
    def test_get_process_command_line_returns_command(self):
        result = get_process_command_line(str(os.getpid()))
        self.assertTrue(result)
        self.assertIn("python", result.lower())

    def test_get_process_command_line_rejects_invalid_pid(self):
        with self.assertRaisesRegex(ValueError, "PID"):
            get_process_command_line("not-a-pid")

    def test_get_process_command_line_rejects_missing_process(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            get_process_command_line("999999999")

    def test_get_process_command_line_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_process_command_line"], get_process_command_line)


class RunCommandToolTests(unittest.TestCase):
    def test_run_command_executes_approved_command(self):
        with patch(
            "gemini_agent.tools.subprocess.run",
            return_value=type("Result", (), {
                "returncode": 0,
                "stdout": "hello\n",
                "stderr": "",
            })(),
        ) as run:
            result = run_command("pwd")
        self.assertEqual(result, "Exit code: 0\nstdout:\nhello")
        run.assert_called_once()

    def test_run_command_rejects_unapproved_command(self):
        with self.assertRaisesRegex(ValueError, "Command is not allowed"):
            run_command("rm file.txt")

    def test_run_command_rejects_unapproved_arguments(self):
        with self.assertRaisesRegex(ValueError, "Arguments are not allowed"):
            run_command("git log")

    def test_run_command_is_registered(self):
        self.assertIs(TOOL_HANDLERS["run_command"], run_command)
        self.assertEqual(RUN_COMMAND_DECLARATION["name"], "run_command")

class CalculatorTests(unittest.TestCase):
    def test_basic_arithmetic(self):
        self.assertEqual(calculator("12 * (3 + 4)"), "84")

    def test_decimal_arithmetic(self):
        self.assertEqual(calculator("10 / 4"), "2.5")

    def test_rejects_python(self):
        with self.assertRaises(ValueError):
            calculator("__import__('os').getcwd()")

    def test_calculator_is_registered(self):
        self.assertIs(TOOL_HANDLERS["calculator"], calculator)
        self.assertIn("calculator", [declaration["name"] for declaration in TOOL_DECLARATIONS])


class CurrentWorkingDirectoryToolTests(unittest.TestCase):
    def test_current_working_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False), patch("os.getcwd", return_value=directory):
                self.assertEqual(get_current_working_directory(), directory)

    def test_current_working_directory_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_current_working_directory"], get_current_working_directory)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_current_working_directory", names)

    def test_python_executable(self):
        with patch("os.sys.executable", "/data/data/com.termux/files/usr/bin/python"):
            self.assertEqual(get_python_executable(), "/data/data/com.termux/files/usr/bin/python")

    def test_python_executable_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_python_executable"], get_python_executable)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_python_executable", names)

    def test_memory_usage_returns_positive_bytes(self):
        self.assertGreater(int(get_memory_usage()), 0)

    def test_memory_usage_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_memory_usage"], get_memory_usage)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_memory_usage", names)

    def test_temp_directory_returns_nonempty_path(self):
        self.assertTrue(get_temp_directory())

    def test_temp_directory_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_temp_directory"], get_temp_directory)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_temp_directory", names)

    def test_process_thread_count_returns_positive_integer(self):
        self.assertGreater(int(get_process_thread_count()), 0)

    def test_process_thread_count_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_process_thread_count"], get_process_thread_count)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_process_thread_count", names)

    def test_user_id_returns_nonnegative_integer(self):
        self.assertGreaterEqual(int(get_user_id()), 0)

    def test_user_id_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_user_id"], get_user_id)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_user_id", names)

    def test_session_id_returns_positive_integer(self):
        self.assertGreater(int(get_session_id()), 0)

    def test_session_id_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_session_id"], get_session_id)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_session_id", names)

    def test_process_group_id_returns_positive_integer(self):
        self.assertGreater(int(get_process_group_id()), 0)

    def test_process_group_id_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_process_group_id"], get_process_group_id)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_process_group_id", names)

    def test_parent_process_id_returns_positive_integer(self):
        self.assertGreater(int(get_parent_process_id()), 0)

    def test_parent_process_id_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_parent_process_id"], get_parent_process_id)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_parent_process_id", names)


class DateTimeToolTests(unittest.TestCase):
    def test_current_datetime_is_registered(self):
        self.assertIs(TOOL_HANDLERS["current_datetime"], current_datetime)
        self.assertIn("current_datetime", [declaration["name"] for declaration in TOOL_DECLARATIONS])

    def test_current_datetime_has_iso_format(self):
        value = current_datetime()
        self.assertRegex(value, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")


class FilesystemToolTests(unittest.TestCase):
    def test_path_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                self.assertEqual(path_exists("notes.txt"), "true")
                self.assertEqual(path_exists("missing.txt"), "false")

    def test_path_exists_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    path_exists("../outside.txt")

    def test_path_exists_is_registered(self):
        self.assertIs(TOOL_HANDLERS["path_exists"], path_exists)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("path_exists", names)

    def test_creates_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = create_directory("archive/nested")
            self.assertEqual(result, "Created directory archive/nested")
            self.assertTrue((Path(directory) / "archive/nested").is_dir())

    def test_create_directory_rejects_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "archive").mkdir()
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "already exists"):
                    create_directory("archive")

    def test_create_directory_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    create_directory("../outside")

    def test_create_directory_is_registered(self):
        self.assertIs(TOOL_HANDLERS["create_directory"], create_directory)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("create_directory", names)

    def test_deletes_empty_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "archive").mkdir()
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = delete_directory("archive")
            self.assertEqual(result, "Deleted directory archive")
            self.assertFalse((root / "archive").exists())

    def test_delete_directory_rejects_non_empty_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "archive").mkdir()
            (root / "archive" / "note.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "not empty"):
                    delete_directory("archive")

    def test_delete_directory_rejects_missing_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "does not exist"):
                    delete_directory("missing")

    def test_delete_directory_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    delete_directory("../outside")

    def test_delete_directory_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["delete_directory"], delete_directory)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("delete_directory", names)

    def test_gets_file_info(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = get_file_info("notes.txt")
            self.assertEqual(result, "Path: notes.txt\\nType: file\\nSize: 5 bytes")

    def test_get_file_info_rejects_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "does not exist"):
                    get_file_info("missing.txt")

    def test_get_file_info_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_file_info"], get_file_info)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_file_info", names)

    def test_lists_directory_recursively(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            nested = root / "nested"
            nested.mkdir()
            (nested / "todo.txt").write_text("todo", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = list_directory_recursive()
            self.assertIn("directory: nested", result)
            self.assertIn("file: nested/todo.txt", result)
            self.assertIn("file: notes.txt", result)

    def test_list_directory_recursive_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    list_directory_recursive("../outside")

    def test_list_directory_recursive_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["list_directory_recursive"], list_directory_recursive)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("list_directory_recursive", names)

    def test_moves_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "archive"
            source.mkdir()
            (source / "note.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = move_directory("archive", "moved/archive")
            self.assertEqual(result, "Moved directory archive to moved/archive")
            self.assertFalse(source.exists())
            self.assertEqual(
                (root / "moved/archive/note.txt").read_text(encoding="utf-8"),
                "hello",
            )

    def test_move_directory_rejects_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "archive").mkdir()
            (root / "other").mkdir()
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "already exists"):
                    move_directory("archive", "other")

    def test_move_directory_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "archive").mkdir()
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    move_directory("archive", "../outside")

    def test_move_directory_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["move_directory"], move_directory)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("move_directory", names)

    def test_copies_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "archive"
            source.mkdir()
            (source / "note.txt").write_text("hello", encoding="utf-8")
            nested = source / "nested"
            nested.mkdir()
            (nested / "todo.txt").write_text("todo", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = copy_directory("archive", "copied/archive")
            self.assertEqual(result, "Copied directory archive to copied/archive")
            self.assertEqual((root / "archive/note.txt").read_text(encoding="utf-8"), "hello")
            self.assertEqual((root / "copied/archive/nested/todo.txt").read_text(encoding="utf-8"), "todo")

    def test_copy_directory_rejects_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "archive").mkdir()
            (root / "other").mkdir()
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "already exists"):
                    copy_directory("archive", "other")

    def test_copy_directory_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "archive").mkdir()
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    copy_directory("archive", "../outside")

    def test_copy_directory_rejects_destination_inside_source(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "archive").mkdir()
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "inside"):
                    copy_directory("archive", "archive/nested")

    def test_copy_directory_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["copy_directory"], copy_directory)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("copy_directory", names)

    def test_counts_file_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = count_file_lines("notes.txt")
            self.assertEqual(result, "3")

    def test_count_file_lines_rejects_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "Not a regular file"):
                    count_file_lines("missing.txt")

    def test_count_file_lines_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    count_file_lines("../outside.txt")

    def test_count_file_lines_is_registered(self):
        self.assertIs(TOOL_HANDLERS["count_file_lines"], count_file_lines)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("count_file_lines", names)

    def test_hashes_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = hash_file("notes.txt")
            self.assertEqual(
                result,
                "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
            )

    def test_hash_file_rejects_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "Not a regular file"):
                    hash_file("missing.txt")

    def test_hash_file_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    hash_file("../outside.txt")

    def test_hash_file_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["hash_file"], hash_file)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("hash_file", names)

    def test_get_disk_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = get_disk_usage(".")
            lines = result.splitlines()
            self.assertEqual(len(lines), 3)
            self.assertRegex(lines[0], r"^Total: \d+ bytes$")
            self.assertRegex(lines[1], r"^Used: \d+ bytes$")
            self.assertRegex(lines[2], r"^Free: \d+ bytes$")

    def test_get_disk_usage_rejects_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "does not exist"):
                    get_disk_usage("missing")

    def test_get_disk_usage_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_disk_usage"], get_disk_usage)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_disk_usage", names)

    def test_get_directory_entry_count(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "one.txt").write_text("1", encoding="utf-8")
            (root / "nested").mkdir()
            (root / "nested" / "two.txt").write_text("2", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                self.assertEqual(get_directory_entry_count("."), "2")

    def test_get_directory_entry_count_rejects_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "one.txt").write_text("1", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "Not a directory"):
                    get_directory_entry_count("one.txt")

    def test_get_directory_entry_count_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    get_directory_entry_count("../outside")

    def test_get_directory_entry_count_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_directory_entry_count"], get_directory_entry_count)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_directory_entry_count", names)

    def test_get_directory_size(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_bytes(b"hello")
            nested = root / "nested"
            nested.mkdir()
            (nested / "todo.txt").write_bytes(b"todo")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = get_directory_size(".")
            self.assertEqual(result, "9 bytes")

    def test_get_directory_size_rejects_file(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "Not a directory"):
                    get_directory_size("notes.txt")

    def test_get_directory_size_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    get_directory_size("../outside")

    def test_get_directory_size_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_directory_size"], get_directory_size)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_directory_size", names)

    def test_get_file_access_time(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = get_file_access_time("notes.txt")
            parsed = __import__("datetime").datetime.fromisoformat(result)
            self.assertIsNotNone(parsed.tzinfo)

    def test_get_file_access_time_rejects_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "does not exist"):
                    get_file_access_time("missing.txt")

    def test_get_file_access_time_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    get_file_access_time("../outside.txt")

    def test_get_file_access_time_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_file_access_time"], get_file_access_time)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_file_access_time", names)

    def test_get_file_modified_time(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "notes.txt"
            path.write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = get_file_modified_time("notes.txt")
            parsed = __import__("datetime").datetime.fromisoformat(result)
            self.assertIsNotNone(parsed.tzinfo)

    def test_get_file_stem(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.TXT").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                self.assertEqual(get_file_stem("notes.TXT"), "notes")

    def test_get_file_stem_rejects_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "Not a regular file"):
                    get_file_stem("missing.txt")

    def test_get_file_stem_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    get_file_stem("../outside.txt")

    def test_get_file_stem_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_file_stem"], get_file_stem)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_file_stem", names)

    def test_get_file_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "nested").mkdir()
            (root / "nested" / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                self.assertEqual(get_file_parent("nested/notes.txt"), "nested")
                self.assertEqual(get_file_parent("nested"), ".")

    def test_get_file_parent_rejects_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "does not exist"):
                    get_file_parent("missing.txt")

    def test_get_file_parent_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    get_file_parent("../outside.txt")

    def test_get_file_parent_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_file_parent"], get_file_parent)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_file_parent", names)

    def test_get_file_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "notes.txt"
            path.write_text("hello", encoding="utf-8")
            path.chmod(0o640)
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                self.assertEqual(get_file_permissions("notes.txt"), "0640")

    def test_get_file_permissions_rejects_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "does not exist"):
                    get_file_permissions("missing.txt")

    def test_get_file_permissions_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    get_file_permissions("../outside.txt")

    def test_get_file_permissions_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_file_permissions"], get_file_permissions)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_file_permissions", names)

    def test_get_file_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.TXT").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                self.assertEqual(get_file_extension("notes.TXT"), ".txt")

    def test_get_file_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "nested").mkdir()
            (root / "nested" / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                self.assertEqual(get_file_name("nested/notes.txt"), "notes.txt")
                self.assertEqual(get_file_name("nested"), "nested")

    def test_get_file_name_rejects_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "does not exist"):
                    get_file_name("missing.txt")

    def test_get_file_name_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    get_file_name("../outside.txt")

    def test_get_file_name_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_file_name"], get_file_name)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_file_name", names)

    def test_get_file_extension_returns_empty_for_extensionless_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                self.assertEqual(get_file_extension("README"), "")

    def test_get_file_extension_rejects_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "Not a regular file"):
                    get_file_extension("missing.txt")

    def test_get_file_extension_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    get_file_extension("../outside.txt")

    def test_get_file_extension_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_file_extension"], get_file_extension)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_file_extension", names)

    def test_get_file_modified_time_rejects_missing_path(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "does not exist"):
                    get_file_modified_time("missing.txt")

    def test_get_file_modified_time_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    get_file_modified_time("../outside.txt")

    def test_get_file_modified_time_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_file_modified_time"], get_file_modified_time)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_file_modified_time", names)

    def test_get_home_directory_returns_nonempty_value(self):
        self.assertTrue(get_home_directory())
        self.assertEqual(get_home_directory(), str(Path.home()))

    def test_get_home_directory_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_home_directory"], get_home_directory)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_home_directory", names)

    def test_get_process_uptime_returns_nonnegative_seconds(self):
        result = get_process_uptime()
        self.assertRegex(result, r"^\d+\.\d{3} seconds$")
        self.assertGreaterEqual(float(result.split()[0]), 0.0)

    def test_get_process_uptime_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_process_uptime"], get_process_uptime)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_process_uptime", names)

    def test_get_umask_returns_octal_value(self):
        result = get_umask()
        self.assertRegex(result, r"^0[0-7]{3}$")

    def test_get_umask_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_umask"], get_umask)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_umask", names)

    def test_get_hostname_returns_nonempty_value(self):
        self.assertTrue(get_hostname())

    def test_get_hostname_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_hostname"], get_hostname)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_hostname", names)

    def test_get_system_info_returns_runtime_details(self):
        result = get_system_info()
        self.assertRegex(result, r"^OS: .+\nArchitecture: .+\nPython: \d+\.\d+\.\d+$")

    def test_get_system_info_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_system_info"], get_system_info)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_system_info", names)

    def test_get_process_id_returns_positive_integer(self):
        self.assertGreater(int(get_process_id()), 0)

    def test_get_process_id_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_process_id"], get_process_id)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_process_id", names)

    def test_get_cpu_count_returns_positive_integer(self):
        self.assertGreater(int(get_cpu_count()), 0)

    def test_get_cpu_count_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_cpu_count"], get_cpu_count)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_cpu_count", names)

    def test_lists_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            (root / "subdir").mkdir()
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = list_directory()
        self.assertIn("file: notes.txt", result)
        self.assertIn("directory: subdir", result)

    def test_reads_text_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello Nova", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                self.assertEqual(read_text_file("notes.txt"), "hello Nova")

    def test_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    read_text_file("../outside.txt")

    def test_rejects_oversized_text_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.txt"
            path.write_bytes(b"x" * (64 * 1024 + 1))
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "larger"):
                    read_text_file("large.txt")

    def test_filesystem_tools_are_registered(self):
        self.assertIs(TOOL_HANDLERS["list_directory"], list_directory)
        self.assertIs(TOOL_HANDLERS["read_text_file"], read_text_file)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertEqual(names[names.index("path_exists"):names.index("find_files") + 1], [
            "path_exists", "create_directory", "delete_directory", "get_file_info", "get_file_access_time", "get_file_modified_time", "get_file_extension", "get_file_name", "get_file_stem", "get_file_permissions", "get_file_parent", "list_directory_recursive", "move_directory", "copy_directory", "hash_file", "count_file_lines", "get_directory_entry_count", "get_disk_usage", "get_directory_size", "list_directory", "read_text_file", "search_text", "write_text_file", "edit_text_file",
            "append_text_file", "copy_file", "move_file", "delete_file", "find_files"
        ])

    def test_copies_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = copy_file("notes.txt", "archive/notes.txt")
            self.assertEqual(result, "Copied notes.txt to archive/notes.txt")
            self.assertEqual((root / "notes.txt").read_text(encoding="utf-8"), "hello")
            self.assertEqual((root / "archive/notes.txt").read_text(encoding="utf-8"), "hello")

    def test_copy_rejects_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            (root / "other.txt").write_text("keep", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "already exists"):
                    copy_file("notes.txt", "other.txt")

    def test_copy_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    copy_file("notes.txt", "../outside.txt")

    def test_copy_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["copy_file"], copy_file)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("copy_file", names)

    def test_moves_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = move_file("notes.txt", "archive/notes.txt")
            self.assertEqual(result, "Moved notes.txt to archive/notes.txt")
            self.assertFalse((root / "notes.txt").exists())
            self.assertEqual(
                (root / "archive/notes.txt").read_text(encoding="utf-8"),
                "hello",
            )

    def test_move_rejects_existing_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            (root / "other.txt").write_text("keep", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "already exists"):
                    move_file("notes.txt", "other.txt")

    def test_move_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    move_file("notes.txt", "../outside.txt")

    def test_move_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["move_file"], move_file)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("move_file", names)

    def test_deletes_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                self.assertEqual(delete_file("notes.txt"), "Deleted notes.txt")
            self.assertFalse((root / "notes.txt").exists())

    def test_delete_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    delete_file("../outside.txt")

    def test_delete_rejects_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "does not exist"):
                    delete_file("missing.txt")

    def test_delete_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["delete_file"], delete_file)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("delete_file", names)

    def test_finds_files_by_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            (root / "image.png").write_bytes(b"data")
            nested = root / "nested"
            nested.mkdir()
            (nested / "todo.txt").write_text("todo", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = find_files("*.txt")
        self.assertIn("notes.txt", result)
        self.assertIn("nested/todo.txt", result)
        self.assertNotIn("image.png", result)

    def test_writes_text_file(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = write_text_file("notes/new.txt", "hello Nova")
                self.assertEqual(result, "Wrote 10 bytes to notes/new.txt")
                self.assertEqual((Path(directory) / "notes/new.txt").read_text(encoding="utf-8"), "hello Nova")

    def test_write_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    write_text_file("../outside.txt", "hello")

    def test_write_rejects_oversized_content(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "larger"):
                    write_text_file("large.txt", "x" * (64 * 1024 + 1))

    def test_write_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["write_text_file"], write_text_file)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("write_text_file", names)

    def test_edits_text_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello Nova", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = edit_text_file("notes.txt", "Nova", "world")
            self.assertEqual(result, "Edited notes.txt")
            self.assertEqual((root / "notes.txt").read_text(encoding="utf-8"), "hello world")

    def test_edit_rejects_missing_text(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "not found"):
                    edit_text_file("notes.txt", "missing", "world")

    def test_edit_rejects_ambiguous_text(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "notes.txt").write_text("hello hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "more than once"):
                    edit_text_file("notes.txt", "hello", "world")

    def test_edit_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["edit_text_file"], edit_text_file)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("edit_text_file", names)

    def test_appends_text_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello", encoding="utf-8")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = append_text_file("notes.txt", " Nova")
                self.assertEqual(result, "Appended 5 bytes to notes.txt")
                self.assertEqual((root / "notes.txt").read_text(encoding="utf-8"), "hello Nova")

    def test_append_creates_missing_file_and_parents(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                append_text_file("notes/new.txt", "first")
                append_text_file("notes/new.txt", " second")
                self.assertEqual(
                    (Path(directory) / "notes/new.txt").read_text(encoding="utf-8"),
                    "first second",
                )

    def test_append_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    append_text_file("../outside.txt", "hello")

    def test_append_rejects_oversized_content(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "larger"):
                    append_text_file("large.txt", "x" * (64 * 1024 + 1))

    def test_append_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["append_text_file"], append_text_file)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("append_text_file", names)

    def test_searches_text_in_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.txt").write_text("hello Nova\nsecond line", encoding="utf-8")
            nested = root / "nested"
            nested.mkdir()
            (nested / "todo.txt").write_text("HELLO again", encoding="utf-8")
            (root / "binary.bin").write_bytes(b"\x00hello")
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                result = search_text("hello")
        self.assertIn("notes.txt:1: hello Nova", result)
        self.assertIn("nested/todo.txt:1: HELLO again", result)
        self.assertNotIn("binary.bin", result)

    def test_search_rejects_empty_pattern(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "empty"):
                    search_text("")

    def test_search_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    search_text("hello", "../")

    def test_search_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["search_text"], search_text)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertEqual(names[names.index("search_text")], "search_text")

    def test_find_rejects_empty_pattern(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "empty"):
                    find_files("")

    def test_find_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"NOVA_FILES_ROOT": directory}, clear=False):
                with self.assertRaisesRegex(ValueError, "outside"):
                    find_files("*.txt", "../")

    def test_find_tool_is_registered(self):
        self.assertIs(TOOL_HANDLERS["find_files"], find_files)
        self.assertIn("find_files", [declaration["name"] for declaration in TOOL_DECLARATIONS])


class GetScreenStateToolTests(unittest.TestCase):
    def test_get_screen_state_parses_display_power(self):
        completed = type(
            "Completed",
            (),
            {"stdout": "Display Power: state=ON\n"},
        )()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed) as run:
            result = get_screen_state()
        self.assertEqual(result, "Screen: ON")
        self.assertEqual(run.call_args.args[0], ["su", "-c", "/system/bin/dumpsys power"])

    def test_get_screen_state_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_screen_state"], get_screen_state)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_screen_state", names)

    
class GetScreenBrightnessModeToolTests(unittest.TestCase):
    def test_get_screen_brightness_mode_parses_android_setting(self):
        completed = type("Completed", (), {"stdout": "1\n"})()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed) as run:
            result = get_screen_brightness_mode()
        self.assertEqual(result, "Brightness mode: Automatic")
        self.assertEqual(run.call_args.args[0], ["su", "-c", "/system/bin/settings get system screen_brightness_mode"])

    def test_get_screen_brightness_mode_falls_back_to_dumpsys(self):
        responses = [
            type("Completed", (), {"stdout": "settings unavailable\n"})(),
            type("Completed", (), {"stdout": "mScreenBrightnessModeSetting=0\n"})(),
        ]
        with patch("gemini_agent.tools.subprocess.run", side_effect=responses) as run:
            result = get_screen_brightness_mode()
        self.assertEqual(result, "Brightness mode: Manual")
        self.assertEqual(run.call_count, 2)

    def test_get_screen_brightness_mode_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_screen_brightness_mode"], get_screen_brightness_mode)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_screen_brightness_mode", names)


class GetScreenOrientationToolTests(unittest.TestCase):
    def test_get_screen_orientation_parses_surface_orientation(self):
        completed = type("Completed", (), {"stdout": "SurfaceOrientation: 1\n"})()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed) as run:
            result = get_screen_orientation()
        self.assertEqual(result, "Screen orientation: Landscape")
        self.assertEqual(
            run.call_args.args[0],
            ["su", "-c", "/system/bin/dumpsys input"],
        )

    def test_get_screen_orientation_falls_back_to_display(self):
        responses = [
            type("Completed", (), {"stdout": "no orientation here\n"})(),
            type("Completed", (), {"stdout": "mDisplayRotation=0\n"})(),
        ]
        with patch("gemini_agent.tools.subprocess.run", side_effect=responses) as run:
            result = get_screen_orientation()
        self.assertEqual(result, "Screen orientation: Portrait")
        self.assertEqual(run.call_count, 2)

    def test_get_screen_orientation_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_screen_orientation"], get_screen_orientation)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_screen_orientation", names)


    def test_get_screen_resolution_parses_wm_size(self):
        completed = type("Completed", (), {"stdout": "Physical size: 720x1612\n"})()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed) as run:
            result = get_screen_resolution()
        self.assertEqual(result, "Screen resolution: 720x1612")
        self.assertEqual(run.call_args.args[0], ["su"])
        self.assertEqual(run.call_args.kwargs["input"], "/system/bin/wm size\n")

    def test_get_screen_resolution_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_screen_resolution"], get_screen_resolution)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_screen_resolution", names)


class GetScreenDensityToolTests(unittest.TestCase):
    def test_get_screen_density_prefers_override_density(self):
        completed = type("Completed", (), {"stdout": "Physical density: 320\nOverride density: 440\n"})()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed) as run:
            result = get_screen_density()
        self.assertEqual(result, "Screen density: 440 dpi")
        self.assertEqual(run.call_args.args[0], ["su"])
        self.assertEqual(run.call_args.kwargs["input"], "/system/bin/wm density\n")

    def test_get_screen_density_falls_back_to_physical_density(self):
        completed = type("Completed", (), {"stdout": "Physical density: 320\n"})()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed):
            self.assertEqual(get_screen_density(), "Screen density: 320 dpi")

    def test_get_screen_density_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_screen_density"], get_screen_density)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_screen_density", names)


class GetScreenRefreshRateToolTests(unittest.TestCase):
    def test_get_screen_refresh_rate_parses_display_rate(self):
        completed = type("Completed", (), {"stdout": "mRefreshRate=120.0\n"})()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed) as run:
            result = get_screen_refresh_rate()
        self.assertEqual(result, "Screen refresh rate: 120 Hz")
        self.assertEqual(
            run.call_args.args[0],
            ["su", "-c", "/system/bin/dumpsys display"],
        )

    def test_get_screen_refresh_rate_falls_back_to_refresh_rate(self):
        completed = type("Completed", (), {"stdout": "refreshRate=60.0\n"})()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed):
            self.assertEqual(get_screen_refresh_rate(), "Screen refresh rate: 60 Hz")

    def test_get_screen_refresh_rate_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_screen_refresh_rate"], get_screen_refresh_rate)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_screen_refresh_rate", names)


class GetScreenTimeoutToolTests(unittest.TestCase):
    def test_get_screen_timeout_parses_android_setting(self):
        completed = type("Completed", (), {"stdout": "600000\n"})()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed) as run:
            result = get_screen_timeout()
        self.assertEqual(result, "Screen timeout: 10 minutes (600000 ms)")
        self.assertEqual(
            run.call_args.args[0],
            ["su", "-c", "/system/bin/settings get system screen_off_timeout"],
        )

    def test_get_screen_timeout_falls_back_to_dumpsys(self):
        responses = [
            type("Completed", (), {"stdout": "settings unavailable\n"})(),
            type("Completed", (), {"stdout": "mScreenOffTimeoutSetting=600000\n"})(),
        ]
        with patch("gemini_agent.tools.subprocess.run", side_effect=responses) as run:
            result = get_screen_timeout()
        self.assertEqual(result, "Screen timeout: 10 minutes (600000 ms)")
        self.assertEqual(run.call_count, 2)

    def test_get_screen_timeout_formats_seconds(self):
        completed = type("Completed", (), {"stdout": "45000\n"})()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed):
            self.assertEqual(get_screen_timeout(), "Screen timeout: 45 seconds (45000 ms)")

    def test_get_screen_timeout_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_screen_timeout"], get_screen_timeout)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_screen_timeout", names)


class GetScreenBrightnessToolTests(unittest.TestCase):
    def test_get_screen_brightness_parses_android_setting(self):
        completed = type("Completed", (), {"stdout": "128\n"})()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed) as run:
            result = get_screen_brightness()
        self.assertEqual(result, "Brightness: 50% (128/255)")
        self.assertEqual(
            run.call_args.args[0],
            ["su", "-c", "/system/bin/settings get system screen_brightness"],
        )

    def test_get_screen_brightness_falls_back_to_float_setting(self):
        responses = [
            type("Completed", (), {"stdout": "null\n"})(),
            type("Completed", (), {"stdout": "0.5\n"})(),
        ]
        with patch("gemini_agent.tools.subprocess.run", side_effect=responses) as run:
            result = get_screen_brightness()
        self.assertEqual(result, "Brightness: 50% (0.50)")
        self.assertEqual(run.call_count, 2)
        self.assertEqual(
            run.call_args_list[1].args[0],
            ["su", "-c", "/system/bin/settings get system screen_brightness_float"],
        )

    def test_get_screen_brightness_parses_display_brightness(self):
        responses = [
            type("Completed", (), {"stdout": "settings unavailable\n"})(),
            type("Completed", (), {"stdout": "null\n"})(),
            type("Completed", (), {"stdout": "Display Brightness=0.09498911\n"})(),
        ]
        with patch("gemini_agent.tools.subprocess.run", side_effect=responses) as run:
            result = get_screen_brightness()
        self.assertEqual(result, "Brightness: 9% (0.09)")
        self.assertEqual(run.call_count, 3)
        self.assertEqual(
            run.call_args_list[2].args[0],
            ["su", "-c", "/system/bin/dumpsys power"],
        )

    def test_get_screen_brightness_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_screen_brightness"], get_screen_brightness)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_screen_brightness", names)


class GetMediaVolumeToolTests(unittest.TestCase):
    def test_get_media_volume_parses_stream_volume(self):
        completed = type(
            "Completed",
            (),
            {
                "stdout": (
                    "Stream volumes (device: index)\n"
                    "    - STREAM_MUSIC:\n"
                    "        streamVolume:15\n"
                )
            },
        )()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed) as run:
            result = get_media_volume()
        self.assertEqual(result, "Media volume: 100% (15/15)")
        self.assertEqual(run.call_args.args[0], ["su"])
        self.assertEqual(run.call_args.kwargs["input"], "/system/bin/dumpsys audio\n")

    def test_get_media_volume_falls_back_to_index_format(self):
        completed = type(
            "Completed",
            (),
            {"stdout": "STREAM_MUSIC: Min: 0 Max: 15 Current: 6\n"},
        )()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed):
            self.assertEqual(get_media_volume(), "Media volume: 40% (6/15)")

    def test_get_media_volume_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_media_volume"], get_media_volume)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_media_volume", names)


class GetSystemBatteryStatusToolTests(unittest.TestCase):
    def test_get_system_battery_status_parses_android_dumpsys(self):
        completed = type(
            "Completed",
            (),
            {
                "stdout": (
                    "AC powered: false\n"
                    "USB powered: true\n"
                    "Wireless powered: false\n"
                    "status: 2\n"
                    "health: 2\n"
                    "level: 87\n"
                    "scale: 100\n"
                    "voltage: 4191\n"
                    "temperature: 253\n"
                )
            },
        )()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed):
            result = get_system_battery_status()
        self.assertEqual(
            result,
            "Level: 87%\n"
            "Status: Charging\n"
            "Health: Good\n"
            "Temperature: 25.3°C\n"
            "Voltage: 4.191 V\n"
            "Power source: USB",
        )

    def test_get_system_battery_status_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_system_battery_status"], get_system_battery_status)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_system_battery_status", names)


class GetSystemCpuUsageToolTests(unittest.TestCase):
    def test_get_system_cpu_usage_returns_percentage(self):
        completed = type("Completed", (), {"stdout": "CPU usage: 37.5%\n"})()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed):
            result = get_system_cpu_usage()
        self.assertEqual(result, "37.50%")

    def test_get_system_cpu_usage_parses_android_top(self):
        completed = type(
            "Completed",
            (),
            {"stdout": "800%cpu   0%user   0%nice   0%sys 800%idle   0%iow   0%irq   0%sirq   0%host\n"},
        )()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed):
            result = get_system_cpu_usage()
        self.assertEqual(result, "0.00%")

    def test_get_system_cpu_usage_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_system_cpu_usage"], get_system_cpu_usage)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_system_cpu_usage", names)


class GetSystemMemoryUsageToolTests(unittest.TestCase):
    def test_get_system_memory_usage_returns_memory_values(self):
        result = get_system_memory_usage()
        self.assertRegex(result, r"^Total: \d+ bytes\nUsed: \d+ bytes\nAvailable: \d+ bytes$")
        values = [int(line.split()[1]) for line in result.splitlines()]
        self.assertEqual(len(values), 3)
        self.assertGreater(values[0], 0)
        self.assertGreaterEqual(values[1], 0)
        self.assertGreaterEqual(values[2], 0)
        self.assertLessEqual(values[1], values[0])
        self.assertLessEqual(values[2], values[0])

    def test_get_system_memory_usage_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_system_memory_usage"], get_system_memory_usage)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_system_memory_usage", names)


class GetSystemSwapUsageToolTests(unittest.TestCase):
    def test_get_system_swap_usage_returns_swap_values(self):
        result = get_system_swap_usage()
        self.assertRegex(result, r"^Total: \d+ bytes\nUsed: \d+ bytes\nFree: \d+ bytes$")
        values = [int(line.split()[1]) for line in result.splitlines()]
        self.assertEqual(len(values), 3)
        self.assertGreaterEqual(values[0], 0)
        self.assertGreaterEqual(values[1], 0)
        self.assertGreaterEqual(values[2], 0)
        self.assertLessEqual(values[1], values[0])
        self.assertLessEqual(values[2], values[0])

    def test_get_system_swap_usage_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_system_swap_usage"], get_system_swap_usage)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_system_swap_usage", names)


class GetSystemBootTimeToolTests(unittest.TestCase):
    def test_get_system_boot_time_returns_local_iso_datetime(self):
        result = get_system_boot_time()
        parsed = __import__("datetime").datetime.fromisoformat(result)
        self.assertIsNotNone(parsed.tzinfo)
        self.assertLessEqual(parsed.timestamp(), __import__("time").time())

    def test_get_system_boot_time_is_registered(self):
        self.assertIs(TOOL_HANDLERS["get_system_boot_time"], get_system_boot_time)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("get_system_boot_time", names)



class VerifyAndroidComponentPresenceTests(unittest.TestCase):
    def test_verifies_component_from_multiple_android_observation_sources(self):
        with patch(
            "gemini_agent.tools.run_root_command",
            side_effect=[
                "topResumedActivity=ActivityRecord{abc com.topjohnwu.magisk/.ui.surequest.SuRequestActivity}",
                "mCurrentFocus=Window{def com.transsion.camera/.app.CaptureActivity}",
                "recent task: com.transsion.camera/.app.CaptureActivity",
            ],
        ) as run:
            result = verify_android_component_presence(
                "com.transsion.camera/.app.CaptureActivity"
            )
        self.assertIn("VERIFIED", result)
        self.assertIn("com.transsion.camera/.app.CaptureActivity", result)
        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                "dumpsys activity activities",
                "dumpsys window windows",
                "dumpsys activity recents",
            ],
        )

    def test_reports_inconclusive_when_component_is_not_observed(self):
        with patch(
            "gemini_agent.tools.run_root_command",
            return_value="topResumedActivity=ActivityRecord com.termux/.app.TermuxActivity",
        ):
            result = verify_android_component_presence(
                "com.transsion.camera/.app.CaptureActivity"
            )
        self.assertIn("INCONCLUSIVE", result)
        self.assertIn("does not prove the component is absent", result)



class ExecuteValidatedAndroidMechanismTests(unittest.TestCase):
    def test_executes_only_after_viable_validation(self):
        with patch(
            "gemini_agent.tools.validate_android_mechanism",
            return_value=(
                "Android mechanism validation (read-only):\\n"
                "Status: VIABLE\\n"
                "Evidence:\\npriority=0 com.transsion.camera/.app.CaptureActivity"
            ),
        ) as validate, patch(
            "gemini_agent.tools.send_android_intent",
            return_value="Android intent android.media.action.IMAGE_CAPTURE started.\\nExit code: 0",
        ) as send, patch(
            "gemini_agent.tools.get_foreground_android_component",
            return_value="Foreground Android component inspection (read-only):\\ntopResumedActivity=ActivityRecord com.transsion.camera/.app.CaptureActivity",
        ) as foreground, patch(
            "gemini_agent.tools.time.sleep",
        ) as sleep:
            result = execute_validated_android_mechanism(
                "capture a photo", "intent:android.media.action.IMAGE_CAPTURE"
            )
        self.assertIn("Validation: VIABLE", result)
        self.assertIn("Exit code: 0", result)
        self.assertIn("VERIFIED: expected Android component is foreground", result)
        validate.assert_called_once_with("capture a photo", "intent:android.media.action.IMAGE_CAPTURE")
        send.assert_called_once_with("android.media.action.IMAGE_CAPTURE")
        foreground.assert_called_once()
        sleep.assert_called_once_with(1)

    def test_blocks_non_intent_mechanisms(self):
        with self.assertRaisesRegex(ValueError, "only validated intent mechanisms"):
            execute_validated_android_mechanism("tap", "ui:com.example:id/button")

    def test_does_not_replan_from_inconclusive_component_observation(self):
        with patch(
            "gemini_agent.tools.validate_android_mechanism",
            return_value=(
                "Android mechanism validation (read-only):\\n"
                "Status: VIABLE\\n"
                "Evidence:\\npriority=0 com.transsion.camera/.app.CaptureActivity"
            ),
        ), patch(
            "gemini_agent.tools.send_android_intent",
            return_value="Android intent android.media.action.IMAGE_CAPTURE started.\\nExit code: 0",
        ), patch(
            "gemini_agent.tools.get_foreground_android_component",
            return_value="Foreground Android component inspection (read-only):\\ntopResumedActivity=ActivityRecord com.topjohnwu.magisk/.ui.surequest.SuRequestActivity",
        ), patch(
            "gemini_agent.tools.verify_android_component_presence",
            return_value="Android component presence verification (read-only): INCONCLUSIVE",
        ), patch(
            "gemini_agent.tools.replan_android_mechanism",
        ) as replan, patch(
            "gemini_agent.tools.time.sleep",
        ):
            result = execute_validated_android_mechanism(
                "open the camera", "intent:android.media.action.IMAGE_CAPTURE"
            )
        self.assertIn("INCONCLUSIVE:", result)
        self.assertNotIn("FAILED: intent launch returned successfully", result)
        replan.assert_not_called()


    def test_reports_failed_postcondition_when_foreground_does_not_match(self):
        with patch(
            "gemini_agent.tools.validate_android_mechanism",
            return_value=(
                "Android mechanism validation (read-only):\\n"
                "Status: VIABLE\\n"
                "Evidence:\\npriority=0 com.transsion.camera/.app.CaptureActivity"
            ),
        ), patch(
            "gemini_agent.tools.send_android_intent",
            return_value="Android intent android.media.action.IMAGE_CAPTURE started.\\nExit code: 0",
        ), patch(
            "gemini_agent.tools.get_foreground_android_component",
            return_value="Foreground Android component inspection (read-only):\\ntopResumedActivity=ActivityRecord com.termux/.app.TermuxActivity",
        ), patch(
            "gemini_agent.tools.verify_android_component_presence",
            return_value="Android component presence verification (read-only): FAILED",
        ), patch(
            "gemini_agent.tools.time.sleep",
        ):
            result = execute_validated_android_mechanism(
                "open the camera", "intent:android.media.action.IMAGE_CAPTURE"
            )
        self.assertIn("FAILED: intent launch returned successfully", result)
        self.assertIn("Expected: com.transsion.camera/.app.CaptureActivity", result)
        self.assertIn("com.termux/.app.TermuxActivity", result)


    def test_recovers_with_an_alternate_discovered_intent_after_postcondition_failure(self):
        validation_calls = []

        def validate(request, mechanism):
            validation_calls.append(mechanism)
            if mechanism == "intent:android.media.action.IMAGE_CAPTURE":
                return (
                    "Android mechanism validation (read-only):\\n"
                    "Status: VIABLE\\n"
                    "Evidence:\\npriority=0 com.transsion.camera/.app.CaptureActivity"
                )
            return (
                "Android mechanism validation (read-only):\\n"
                "Status: VIABLE\\n"
                "Evidence:\\npriority=0 com.transsion.camera/.app.CaptureActivity"
            )

        foregrounds = iter([
            "Foreground Android component inspection (read-only):\\ntopResumedActivity=ActivityRecord com.termux/.app.TermuxActivity",
            "Foreground Android component inspection (read-only):\\ntopResumedActivity=ActivityRecord com.transsion.camera/.app.CaptureActivity",
        ])
        with patch(
            "gemini_agent.tools.validate_android_mechanism",
            side_effect=validate,
        ), patch(
            "gemini_agent.tools.send_android_intent",
            side_effect=[
                "Android intent android.media.action.IMAGE_CAPTURE started.\\nExit code: 0",
                "Android intent android.media.action.STILL_IMAGE_CAMERA started.\\nExit code: 0",
            ],
        ) as send, patch(
            "gemini_agent.tools.discover_android_mechanisms",
            return_value=(
                "Android mechanism discovery (read-only):\n"
                "Discovered bounded intent mechanisms:\n"
                "intent:android.media.action.IMAGE_CAPTURE\n"
                "intent:android.media.action.STILL_IMAGE_CAMERA"
            ),
        ), patch(
            "gemini_agent.tools.get_foreground_android_component",
            side_effect=lambda: next(foregrounds),
        ), patch(
            "gemini_agent.tools.verify_android_component_presence",
            return_value="Android component presence verification (read-only): FAILED",
        ), patch(
            "gemini_agent.tools.time.sleep",
        ):
            result = execute_validated_android_mechanism(
                "open the camera", "intent:android.media.action.IMAGE_CAPTURE"
            )

        self.assertIn("Replan: selected alternate viable mechanism.", result)
        self.assertIn("Post-action verification: VERIFIED: expected Android component is foreground", result)
        self.assertIn("Recovery: discovered an alternate viable Android intent", result)
        self.assertEqual(
            validation_calls,
            [
                "intent:android.media.action.IMAGE_CAPTURE",
                "intent:android.media.action.STILL_IMAGE_CAMERA",
            ],
        )
        self.assertEqual(send.call_count, 2)

    def test_blocks_non_viable_mechanism_without_action(self):
        with patch(
            "gemini_agent.tools.validate_android_mechanism",
            return_value="Android mechanism validation (read-only):\\nStatus: NOT VIABLE",
        ), patch("gemini_agent.tools.send_android_intent") as send:
            result = execute_validated_android_mechanism(
                "capture a photo", "intent:android.media.action.IMAGE_CAPTURE"
            )
        self.assertIn("execution blocked", result)
        send.assert_not_called()

    def test_is_registered(self):
        self.assertIs(TOOL_HANDLERS["execute_validated_android_mechanism"], execute_validated_android_mechanism)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("execute_validated_android_mechanism", names)


class VerifyCommandResultToolTests(unittest.TestCase):
    def test_verify_command_result_passes_when_expected_text_is_present(self):
        result = verify_command_result("Exit code: 0\nstdout:\n/system/bin/dumpsys", "/system/bin/dumpsys")
        self.assertEqual(result, "Verification: passed. Expected text found: /system/bin/dumpsys")

    def test_verify_command_result_fails_when_expected_text_is_missing(self):
        result = verify_command_result("Exit code: 1\nstderr:\nnot found", "/system/bin/dumpsys")
        self.assertEqual(result, "Verification: failed. Expected text not found: /system/bin/dumpsys")

    def test_verify_command_result_is_registered(self):
        self.assertIs(TOOL_HANDLERS["verify_command_result"], verify_command_result)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("verify_command_result", names)


class RetryCommandToolTests(unittest.TestCase):
    def test_retry_command_returns_after_successful_first_attempt(self):
        with patch("gemini_agent.tools.run_command", return_value="Exit code: 0\nstdout:\nok") as run:
            result = retry_command("pwd")
        self.assertEqual(result, "Attempts: 1\nExit code: 0\nstdout:\nok")
        run.assert_called_once_with("pwd")

    def test_retry_command_retries_failed_result_once(self):
        with patch(
            "gemini_agent.tools.run_command",
            side_effect=["Exit code: 1\nstderr:\nfailed", "Exit code: 0\nstdout:\nrecovered"],
        ) as run:
            result = retry_command("pwd")
        self.assertEqual(result, "Attempts: 2\nExit code: 0\nstdout:\nrecovered")
        self.assertEqual(run.call_count, 2)

    def test_retry_command_retries_timeout_once(self):
        with patch(
            "gemini_agent.tools.run_command",
            side_effect=[RuntimeError("Command timed out after 5 seconds."), "Exit code: 0"],
        ) as run:
            result = retry_command("pwd")
        self.assertEqual(result, "Attempts: 2\nExit code: 0")
        self.assertEqual(run.call_count, 2)

    def test_retry_command_is_registered(self):
        self.assertIs(TOOL_HANDLERS["retry_command"], retry_command)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("retry_command", names)



class RecoverCommandToolTests(unittest.TestCase):
    def test_recover_command_verifies_optional_postcondition(self):
        with patch("gemini_agent.tools.run_command", return_value="Exit code: 0\nstdout:\nexpected-value") as run:
            result = recover_command("pwd", expected="expected-value")
        self.assertIn("Outcome: VERIFIED", result)
        self.assertIn("Postcondition: VERIFIED: expected text found: expected-value", result)
        run.assert_called_once_with("pwd")

    def test_recover_command_retries_when_postcondition_fails(self):
        with patch(
            "gemini_agent.tools.run_command",
            side_effect=[
                "Exit code: 0\nstdout:\nwrong output",
                "Exit code: 0\nstdout:\nPython 3.14.6",
            ],
        ) as run:
            result = recover_command("python --version", expected="Python")
        self.assertIn("retried once", result)
        self.assertIn("First attempt: FAILED", result)
        self.assertIn("stdout:\nwrong output", result)
        self.assertIn("Postcondition: FAILED: expected text not found: Python", result)
        self.assertIn("Second attempt: VERIFIED", result)
        self.assertIn("stdout:\nPython 3.14.6", result)
        self.assertIn("Postcondition: VERIFIED: expected text found: Python", result)
        self.assertIn("Outcome: VERIFIED", result)
        self.assertEqual(run.call_count, 2)

    def test_recover_command_rejects_success_without_expected_postcondition(self):
        with patch("gemini_agent.tools.run_command", return_value="Exit code: 0\nstdout:\nother-value") as run:
            result = recover_command("pwd", expected="expected-value")
        self.assertIn("Outcome: FAILED", result)
        self.assertIn("Postcondition: FAILED: expected text not found: expected-value", result)
        self.assertIn("Attempts: 2", result)
        self.assertEqual(run.call_count, 2)

    def test_recover_command_returns_success_without_recovery(self):
        with patch("gemini_agent.tools.run_command", return_value="Exit code: 0\nstdout:\nok") as run:
            result = recover_command("pwd")
        self.assertIn("Recovery: none needed.", result)
        self.assertIn("Attempts: 1", result)
        run.assert_called_once_with("pwd")

    def test_recover_command_discovers_missing_executable(self):
        with patch("gemini_agent.tools.run_command", return_value="Exit code: 127\nstderr:\ncommand not found") as run:
            with patch("gemini_agent.tools.find_executable", return_value="Executable: /system/bin/dumpsys") as find:
                with patch("gemini_agent.tools.run_root_command", side_effect=[RuntimeError("Root command timed out after 5 seconds."), "Exit code: 0\nstdout:\nsvc1\nsvc2"]) as root:
                    result = recover_command("dumpsys")
        self.assertIn("executable or path not found", result)
        self.assertIn("Recovery: bare dumpsys was unbounded; adapted to the bounded manual-su service-list diagnostic and command succeeded.", result)
        self.assertIn("svc1", result)
        run.assert_called_once_with("dumpsys")
        find.assert_called_once_with("dumpsys")
        self.assertEqual(root.call_args_list[0].args, ("dumpsys",))
        self.assertEqual(root.call_args_list[1].args, ("dumpsys -l",))


    def test_recover_command_retries_timeout(self):
        with patch("gemini_agent.tools.run_command", side_effect=[RuntimeError("Command timed out after 5 seconds."), "Exit code: 0"]) as run:
            result = recover_command("pwd")
        self.assertIn("Diagnosis: command timed out", result)
        self.assertIn("Attempts: 2", result)
        self.assertEqual(run.call_count, 2)

    def test_recover_command_executes_discovered_executable_path(self):
        with patch(
            "gemini_agent.tools.run_command",
            side_effect=[RuntimeError("Command failed to start: No such file or directory"), "Exit code: 0\\nstdout:\\nPython 3"],
        ) as run:
            with patch("gemini_agent.tools.find_executable", return_value="Executable: /system/bin/python"):
                result = recover_command("python --version")
        self.assertIn("Recovery: executable path discovered and command succeeded.", result)
        self.assertIn("Exit code: 0", result)
        self.assertEqual(run.call_args_list[1].args, ("/system/bin/python --version",))

    def test_recover_command_is_registered(self):
        self.assertIs(TOOL_HANDLERS["recover_command"], recover_command)
        names = [declaration["name"] for declaration in TOOL_DECLARATIONS]
        self.assertIn("recover_command", names)


if __name__ == "__main__":
    unittest.main()