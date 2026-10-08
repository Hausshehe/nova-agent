import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gemini_agent.constructed_action import (
    CONSTRUCTED_ACTION_DECLARATION,
    execute_constructed_action,
)


class ConstructedActionTests(unittest.TestCase):
    def test_workspace_action_executes_structured_argv_without_shell(self):
        with tempfile.TemporaryDirectory() as root:
            os.environ["NOVA_FILES_ROOT"] = root
            try:
                completed = type("Completed", (), {"returncode": 0, "stdout": "created\n", "stderr": ""})()
                with patch("gemini_agent.constructed_action.shutil.which", return_value="/bin/touch"), patch(
                    "gemini_agent.constructed_action.subprocess.run", return_value=completed
                ) as run:
                    result = execute_constructed_action(
                        executable="touch",
                        arguments=["artifact.txt"],
                        working_directory=".",
                        timeout_seconds=5,
                        mutation_scope="WORKSPACE_MUTATION",
                        expected_effects=["artifact.txt exists"],
                        evidence_requirements=["exit code is 0", "artifact exists"],
                    )
                self.assertIn("Exit code: 0", result)
                self.assertEqual(run.call_args.args[0], [str(Path("/bin/touch").resolve()), "artifact.txt"])
                self.assertFalse(run.call_args.kwargs["shell"])
                self.assertEqual(Path(run.call_args.kwargs["cwd"]), Path(root).resolve())
            finally:
                os.environ.pop("NOVA_FILES_ROOT", None)

    def test_shell_and_interpreter_executables_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Interpreter or shell"):
            execute_constructed_action(
                "sh", ["-c", "touch bad"], ".", 5, "WORKSPACE_MUTATION", ["bad"], ["exists"]
            )
        with self.assertRaisesRegex(ValueError, "Interpreter or shell"):
            execute_constructed_action(
                "python", ["-c", "print(1)"], ".", 5, "WORKSPACE_MUTATION", [], ["exit 0"]
            )

    def test_shell_composition_in_argument_is_rejected(self):
        with patch("gemini_agent.constructed_action.shutil.which", return_value="/bin/touch"):
            with self.assertRaisesRegex(ValueError, "shell syntax"):
                execute_constructed_action(
                    "touch", ["safe;rm"], ".", 5, "WORKSPACE_MUTATION", [], ["exit 0"]
                )

    def test_working_directory_cannot_escape_root(self):
        with tempfile.TemporaryDirectory() as root:
            os.environ["NOVA_FILES_ROOT"] = root
            with self.assertRaisesRegex(ValueError, "outside Nova"):
                execute_constructed_action(
                    "touch", ["x"], "..", 5, "WORKSPACE_MUTATION", [], ["exit 0"]
                )
            os.environ.pop("NOVA_FILES_ROOT", None)

    def test_unapproved_scope_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "not currently executable"):
            execute_constructed_action(
                "touch", ["x"], ".", 5, "DEVICE_STATE_MUTATION", [], ["exit 0"]
            )

    def test_timeout_is_bounded(self):
        with self.assertRaisesRegex(ValueError, "between 1 and 30"):
            execute_constructed_action(
                "touch", ["x"], ".", 31, "WORKSPACE_MUTATION", [], ["exit 0"]
            )

    def test_declaration_is_registered_shape(self):
        self.assertEqual(CONSTRUCTED_ACTION_DECLARATION["name"], "execute_constructed_action")
        required = set(CONSTRUCTED_ACTION_DECLARATION["parameters"]["required"])
        self.assertTrue({
            "executable", "arguments", "working_directory", "timeout_seconds",
            "mutation_scope", "expected_effects", "evidence_requirements",
        } <= required)


if __name__ == "__main__":
    unittest.main()
