"""Tests for bounded Android UI mechanism execution."""

import unittest
from unittest.mock import patch

from gemini_agent.android_ui import execute_validated_android_ui_mechanism


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
                "Exit code: 0\nstdout:\n" + hierarchy,
                "Exit code: 0\nstdout:\nTap complete",
                "Exit code: 0\nstdout:\n",
            ],
        ) as run:
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
        self.assertEqual(
            run.call_args_list[2].args[0],
            "input tap 60 50",
        )


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
                "Exit code: 0\nstdout:\n" + hierarchy,
                "Exit code: 0\nstdout:\nTap complete",
                "Exit code: 0\nstdout:\n",
            ],
        ) as run:
            result = execute_validated_android_ui_mechanism(
                "activate the Termux extra keys surface",
                "ui:com.termux:id/extra_keys",
            )

        self.assertIn("Resolved bounds: [0,1400][720,1612]", result)
        self.assertEqual(run.call_args_list[2].args[0], "input tap 360 1506")

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
                "Exit code: 0\nstdout:\n" + hierarchy,
                "Exit code: 0\nstdout:\nTap complete",
                "Exit code: 0\nstdout:\n",
            ],
        ) as run:
            result = execute_validated_android_ui_mechanism(
                "activate the ESC extra key",
                "ui-text:ESC",
            )

        self.assertIn("Resolved bounds: [6,812][100,962]", result)
        self.assertEqual(run.call_args_list[2].args[0], "input tap 53 887")

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
