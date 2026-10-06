import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gemini_agent.client import GeminiClient
from gemini_agent.learning import (
    rank_with_verified_android_experience,
    record_verified_android_experience,
)
from gemini_agent.tools import execute_android_mechanism


class VerifiedAndroidExperienceTests(unittest.TestCase):
    def test_records_only_explicitly_verified_experience(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = Path(temp_dir) / "experiences.json"
            with patch("gemini_agent.learning._experience_path", return_value=store):
                result = record_verified_android_experience(
                    "control the phone camera",
                    "intent:android.media.action.IMAGE_CAPTURE",
                    "Post-action verification: VERIFIED: expected component is foreground.",
                )
            entries = json.loads(store.read_text(encoding="utf-8"))
        self.assertIn("Verified Android experience learned.", result)
        self.assertEqual(entries[-1]["mechanism"], "intent:android.media.action.IMAGE_CAPTURE")
        self.assertEqual(entries[-1]["status"], "VERIFIED")

    def test_does_not_learn_inconclusive_experience(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = Path(temp_dir) / "experiences.json"
            with patch("gemini_agent.learning._experience_path", return_value=store):
                result = record_verified_android_experience(
                    "control the phone camera",
                    "intent:android.media.action.IMAGE_CAPTURE",
                    "Post-action verification: INCONCLUSIVE",
                )
            self.assertIn("not learned", result)
            self.assertFalse(store.exists())

    def test_verified_experience_changes_future_ranking_for_similar_request(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = Path(temp_dir) / "experiences.json"
            store.write_text(json.dumps([{
                "request": "control the phone camera",
                "mechanism": "intent:android.media.action.IMAGE_CAPTURE",
                "status": "VERIFIED",
                "evidence": "Post-action verification: VERIFIED",
                "recorded_at": "2026-10-06T18:00:00+00:00",
            }]), encoding="utf-8")
            with patch("gemini_agent.learning._experience_path", return_value=store):
                ranked = rank_with_verified_android_experience(
                    "control phone camera",
                    ["ui-text:CTRL", "intent:android.media.action.IMAGE_CAPTURE"],
                )
        self.assertEqual(ranked[0], "intent:android.media.action.IMAGE_CAPTURE")

    def test_dissimilar_experience_does_not_change_ranking(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = Path(temp_dir) / "experiences.json"
            store.write_text(json.dumps([{
                "request": "open the calculator",
                "mechanism": "intent:some.calculator.ACTION",
                "status": "VERIFIED",
                "evidence": "Post-action verification: VERIFIED",
            }]), encoding="utf-8")
            candidates = ["ui-text:CTRL", "intent:android.media.action.IMAGE_CAPTURE"]
            with patch("gemini_agent.learning._experience_path", return_value=store):
                ranked = rank_with_verified_android_experience("control the phone camera", candidates)
        self.assertEqual(ranked, candidates)

    def test_android_execution_learns_only_verified_result(self):
        with patch(
            "gemini_agent.tools.execute_validated_android_mechanism",
            return_value="Android mechanism execution:\nPost-action verification: VERIFIED: expected component is foreground.",
        ), patch(
            "gemini_agent.tools.record_verified_android_experience",
            return_value="Verified Android experience learned.",
        ) as recorder:
            result = execute_android_mechanism(
                "control the phone camera",
                "intent:android.media.action.IMAGE_CAPTURE",
                allow_recovery=False,
            )
        self.assertIn("Verified Android experience learned.", result)
        recorder.assert_called_once()

    def test_client_routes_learning_and_ranking_locally(self):
        with patch.dict(
            os.environ,
            {"CLOUDFLARE_API_TOKEN": "token", "CLOUDFLARE_ACCOUNT_ID": "account"},
            clear=True,
        ), patch("urllib.request.urlopen") as open_url:
            client = GeminiClient()
            record = client.ask(
                'Record verified Android experience for request "control the phone camera" '
                'using mechanism intent:android.media.action.IMAGE_CAPTURE '
                'with verification: Post-action verification: VERIFIED: bounded test evidence.'
            )
            rank = client.ask(
                'Rank Android mechanisms for request "control the phone camera" '
                'candidates: ui-text:CTRL, intent:android.media.action.IMAGE_CAPTURE'
            )
        self.assertIn("Verified Android experience learned.", record)
        self.assertIn("intent:android.media.action.IMAGE_CAPTURE", rank)
        self.assertEqual(
            rank.split("intent:android.media.action.IMAGE_CAPTURE")[0].strip(),
            "['",
        )
        open_url.assert_not_called()
