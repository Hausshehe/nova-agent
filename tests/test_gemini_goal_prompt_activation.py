import unittest
from unittest.mock import patch

from gemini_agent.client import GeminiClient


class GoalPromptActivationTests(unittest.TestCase):
    def test_calculator_continuation_with_verified_wording_activates_goal(self):
        prompt = (
            "Continue from the real current environment and the existing calculator-app goal. "
            "Inspect installed dependencies and existing workspace artifacts first. "
            "Use your registered dependency-discovery and package-acquisition tools to install "
            "necessary packages from configured Termux repositories. "
            "Choose the smallest viable Android build strategy, create the source and configuration "
            "files, build an installable APK, and run actual tests for addition, subtraction, "
            "multiplication, and division. After each action, inspect its result and adapt to failures "
            "instead of repeating discovery. Continue until the APK and arithmetic tests are "
            "independently verified or a genuine environmental blocker is demonstrated. "
            "Do not ask me to install dependencies manually. Report the workspace, source files, "
            "build command, APK path, test results, and unresolved blockers. "
            "Never claim success without evidence."
        )
        with patch.dict(
            "os.environ",
            {
                "NOVA_PROVIDER": "cloudflare",
                "CLOUDFLARE_API_TOKEN": "test-token",
                "CLOUDFLARE_ACCOUNT_ID": "test-account",
            },
        ):
            client = GeminiClient()
        with patch.object(client, "_generate_cloudflare", return_value="stub response"):
            self.assertEqual(client.ask(prompt), "stub response")

        self.assertIsNotNone(client.goal_state)
        self.assertEqual(client.goal_state.status, "ACTIVE")
        condition = client.goal_state.success_condition.lower()
        for criterion in ("apk", "addition", "subtraction", "multiplication", "division"):
            self.assertIn(criterion, condition)


if __name__ == "__main__":
    unittest.main()
