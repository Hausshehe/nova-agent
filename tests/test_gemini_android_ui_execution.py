"""Tests for bounded Android UI mechanism execution."""

import unittest
from unittest.mock import patch

from gemini_agent.android_ui import execute_validated_android_ui_mechanism
from gemini_agent.tools import _run_bounded_ui_tap, TOOL_DECLARATIONS, TOOL_HANDLERS


class AndroidUiExecutionTests(unittest.TestCase):
    def test_executes_validated_clickable_resource_id(self):
        hierarchy = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<hierarchy><node class="android.widget.Button" '
            'resource-id="com.example:id/action" clickable="true" enabled="true" '
            'bounds="[10,20][110,80]" /></hierarchy>'
        )
        with patch(
            "gemini_agent.android_ui.validate_android_mechanism",
            return_value="Status: VIABLE",
        ) as validate, patch(
            "gemini_agent.android_ui.run_root_command",
            side_effect=[
                "Exit code: 0\nstdout:\nUI dump complete",
                "Exit code: 0\nstdout:\nTap complete",
                "Exit code: 0\nstdout:\n",
            ],
        ) as run, patch(
            "gemini_agent.android_ui._read_bounded_root_file",
            return_value=hierarchy,
        ), patch(
            "gemini_agent.android_ui._run_bounded_ui_tap",
            return_value="Exit code: 0\nstdout:\nTap complete",
        ) as tap:
            result = execute_validated_android_ui_mechanism(
                "activate the action control",
                "ui:com.example:id/action",
            )

        validate.assert_called_once_with(
            "activate the action control",
            "ui:com.example:id/action",
        )
        self.assertIn("Resolved bounds: [10,20][110,80]", result)
        self.assertIn("Tap result:", result)
        self.assertEqual(run.call_args_list[0].args[0], "uiautomator dump /data/local/tmp/nova-ui-execution.xml")
        tap.assert_called_once_with(60, 50)


    def test_executes_enabled_non_clickable_resource_id(self):
        hierarchy = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<hierarchy><node class="com.termux.ExtraKeysView" '
            'resource-id="com.termux:id/extra_keys" clickable="false" enabled="true" '
            'bounds="[0,1400][720,1612]" /></hierarchy>'
        )
        with patch(
            "gemini_agent.android_ui.validate_android_mechanism",
            return_value="Status: VIABLE",
        ), patch(
            "gemini_agent.android_ui.run_root_command",
            side_effect=[
                "Exit code: 0\nstdout:\nUI dump complete",
                "Exit code: 0\nstdout:\nTap complete",
                "Exit code: 0\nstdout:\n",
            ],
        ) as run, patch(
            "gemini_agent.android_ui._read_bounded_root_file",
            return_value=hierarchy,
        ), patch(
            "gemini_agent.android_ui._run_bounded_ui_tap",
            return_value="Exit code: 0\nstdout:\nTap complete",
        ) as tap:
            result = execute_validated_android_ui_mechanism(
                "activate the Termux extra keys surface",
                "ui:com.termux:id/extra_keys",
            )

        self.assertIn("Resolved bounds: [0,1400][720,1612]", result)
        self.assertEqual(run.call_args_list[0].args[0], "uiautomator dump /data/local/tmp/nova-ui-execution.xml")
        tap.assert_called_once_with(360, 1506)

    def test_executes_ui_text_selector(self):
        hierarchy = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<hierarchy><node class="android.widget.Button" '
            'text="ESC" resource-id="" clickable="true" enabled="true" '
            'bounds="[6,812][100,962]" /></hierarchy>'
        )
        with patch(
            "gemini_agent.android_ui.validate_android_mechanism",
            return_value="Status: VIABLE",
        ), patch(
            "gemini_agent.android_ui.run_root_command",
            side_effect=[
                "Exit code: 0\nstdout:\nUI dump complete",
                "Exit code: 0\nstdout:\nTap complete",
                "Exit code: 0\nstdout:\n",
            ],
        ) as run, patch(
            "gemini_agent.android_ui._read_bounded_root_file",
            return_value=hierarchy,
        ), patch(
            "gemini_agent.android_ui._run_bounded_ui_tap",
            return_value="Exit code: 0\nstdout:\nTap complete",
        ) as tap:
            result = execute_validated_android_ui_mechanism(
                "activate the ESC extra key",
                "ui-text:ESC",
            )

        self.assertIn("Resolved bounds: [6,812][100,962]", result)
        self.assertEqual(run.call_args_list[0].args[0], "uiautomator dump /data/local/tmp/nova-ui-execution.xml")
        tap.assert_called_once_with(53, 887)

    def test_reports_unverified_when_target_attributes_do_not_change(self):
        hierarchy = (
            '<hierarchy><node class="android.widget.Button" text="CTRL" '
            'resource-id="" enabled="true" clickable="true" selected="false" '
            'checked="false" focused="false" bounds="[107,887][208,962]" /></hierarchy>'
        )
        with patch(
            "gemini_agent.android_ui.validate_android_mechanism",
            return_value="Status: VIABLE",
        ), patch(
            "gemini_agent.android_ui.run_root_command",
            side_effect=["Exit code: 0", "Exit code: 0", "Exit code: 0"],
        ), patch(
            "gemini_agent.android_ui._read_bounded_root_file",
            return_value=hierarchy,
        ), patch(
            "gemini_agent.android_ui._run_bounded_ui_tap",
            return_value="Exit code: 0",
        ):
            result = execute_validated_android_ui_mechanism(
                "activate CTRL",
                "ui-text:CTRL",
            )
        self.assertIn(
            "Post-action verification: UNVERIFIED: target UI node attributes were unchanged after the tap.",
            result,
        )

    def test_reports_verified_when_target_attributes_change(self):
        before = (
            '<hierarchy><node class="android.widget.Button" text="CTRL" '
            'resource-id="" enabled="true" clickable="true" selected="false" '
            'checked="false" focused="false" bounds="[107,887][208,962]" /></hierarchy>'
        )
        after = (
            '<hierarchy><node class="android.widget.Button" text="CTRL" '
            'resource-id="" enabled="true" clickable="true" selected="true" '
            'checked="false" focused="false" bounds="[107,887][208,962]" /></hierarchy>'
        )
        with patch(
            "gemini_agent.android_ui.validate_android_mechanism",
            return_value="Status: VIABLE",
        ), patch(
            "gemini_agent.android_ui.run_root_command",
            side_effect=["Exit code: 0", "Exit code: 0", "Exit code: 0"],
        ), patch(
            "gemini_agent.android_ui._read_bounded_root_file",
            side_effect=[before, after],
        ), patch(
            "gemini_agent.android_ui._run_bounded_ui_tap",
            return_value="Exit code: 0",
        ):
            result = execute_validated_android_ui_mechanism(
                "activate CTRL",
                "ui-text:CTRL",
            )
        self.assertIn(
            "Post-action verification: VERIFIED: target UI node attributes changed after the tap.",
            result,
        )

    def test_bounded_ui_tap_rejects_out_of_range_coordinates(self):
        with self.assertRaisesRegex(ValueError, "outside the bounded screen range"):
            _run_bounded_ui_tap(10001, 887)

    def test_bounded_ui_tap_allows_valid_coordinates(self):
        completed = type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        with patch("gemini_agent.tools.subprocess.run", return_value=completed) as run:
            result = _run_bounded_ui_tap(53, 887)

        self.assertIn("Exit code: 0", result)
        run.assert_called_once_with(
            ["su"],
            input="input tap 53 887\nexit\n",
            stdout=unittest.mock.ANY,
            stderr=unittest.mock.ANY,
            text=True,
            timeout=unittest.mock.ANY,
            check=False,
        )

    def test_ui_executor_is_exposed_as_a_tool(self):
        declaration = next(d for d in TOOL_DECLARATIONS if d["name"] == "execute_validated_android_ui_mechanism")
        self.assertIn("ui-text:<text>", declaration["parameters"]["properties"]["mechanism"]["description"])
        self.assertTrue(callable(TOOL_HANDLERS["execute_validated_android_ui_mechanism"]))

    def test_blocks_non_ui_mechanisms(self):
        with self.assertRaisesRegex(ValueError, "only validated ui"):
            execute_validated_android_ui_mechanism(
                "open camera",
                "intent:android.media.action.IMAGE_CAPTURE",
            )

    def test_blocks_non_viable_without_tap(self):
        with patch(
            "gemini_agent.android_ui.validate_android_mechanism",
            return_value="Status: NOT VIABLE",
        ), patch("gemini_agent.android_ui.run_root_command") as run:
            result = execute_validated_android_ui_mechanism(
                "activate missing control",
                "ui:missing",
            )

        self.assertIn("blocked", result.lower())
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
