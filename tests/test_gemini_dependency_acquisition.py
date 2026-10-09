import os
import unittest
from unittest.mock import patch

from gemini_agent.dependency_acquisition import acquire_termux_packages


class DependencyAcquisitionTests(unittest.TestCase):
    def test_inspect_uses_configured_package_manager_without_shell(self):
        completed = type("Completed", (), {"returncode": 0, "stdout": "Package: gradle", "stderr": ""})()
        with patch("gemini_agent.dependency_acquisition.shutil.which", return_value="/usr/bin/pkg"), patch(
            "gemini_agent.dependency_acquisition.subprocess.run", return_value=completed
        ) as run:
            result = acquire_termux_packages(["gradle"], mode="inspect")
        self.assertIn("Package operation: INSPECT", result)
        self.assertIn("Exit code: 0", result)
        self.assertEqual(run.call_args.args[0], ["/usr/bin/pkg", "show", "gradle"])
        self.assertFalse(run.call_args.kwargs["shell"])

    def test_install_is_allowlisted_and_uses_configured_repository(self):
        completed = type("Completed", (), {"returncode": 0, "stdout": "installed", "stderr": ""})()
        with patch("gemini_agent.dependency_acquisition.shutil.which", return_value="/usr/bin/pkg"), patch(
            "gemini_agent.dependency_acquisition.subprocess.run", return_value=completed
        ) as run:
            result = acquire_termux_packages(["openjdk-21", "gradle"], mode="install", timeout_seconds=90)
        self.assertIn("independently verify", result)
        self.assertEqual(run.call_args.args[0], ["/usr/bin/pkg", "install", "-y", "openjdk-21", "gradle"])
        self.assertEqual(run.call_args.kwargs["timeout"], 90)

    def test_rejects_arbitrary_package_names(self):
        with self.assertRaisesRegex(ValueError, "not in the dependency-install allowlist"):
            acquire_termux_packages(["curl;sh"], mode="install")

    def test_rejects_unapproved_modes_and_unbounded_timeout(self):
        with self.assertRaisesRegex(ValueError, "mode must"):
            acquire_termux_packages(["gradle"], mode="download")
        with self.assertRaisesRegex(ValueError, "between 1 and 120"):
            acquire_termux_packages(["gradle"], mode="install", timeout_seconds=121)

    def test_rejects_empty_or_oversized_package_lists(self):
        with self.assertRaisesRegex(ValueError, "1 to 12"):
            acquire_termux_packages([], mode="inspect")
        with self.assertRaisesRegex(ValueError, "1 to 12"):
            acquire_termux_packages(["gradle"] * 13, mode="inspect")

    def test_reports_failed_install_without_claiming_success(self):
        completed = type("Completed", (), {"returncode": 100, "stdout": "", "stderr": "package unavailable"})()
        with patch("gemini_agent.dependency_acquisition.shutil.which", return_value="/usr/bin/pkg"), patch(
            "gemini_agent.dependency_acquisition.subprocess.run", return_value=completed
        ):
            result = acquire_termux_packages(["gradle"], mode="install")
        self.assertIn("Exit code: 100", result)
        self.assertIn("No success claimed", result)


if __name__ == "__main__":
    unittest.main()
