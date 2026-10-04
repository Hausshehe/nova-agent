"""Offline tests for local structured memory."""

import json
import tempfile
import unittest
from pathlib import Path

from gemini_agent.memory import ConversationMemory


class ConversationMemoryTests(unittest.TestCase):
    def test_saves_and_reloads_exchange(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            memory = ConversationMemory(path)
            memory.add_exchange("My favorite color is purple", "Purple!")
            loaded = ConversationMemory(path)
            self.assertEqual(loaded.history[0]["parts"][0]["text"], "My favorite color is purple")
            self.assertEqual(loaded.history[1]["parts"][0]["text"], "Purple!")

    def test_saves_and_reloads_structured_fact(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            memory = ConversationMemory(path)
            memory.remember_fact("favorite_color", "purple")
            loaded = ConversationMemory(path)
            self.assertEqual(loaded.facts, {"favorite_color": "purple"})
            self.assertIn("favorite_color: purple", loaded.context()[0]["parts"][0]["text"])

    def test_limits_history(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = ConversationMemory(Path(directory) / "memory.json", max_messages=2)
            memory.add_exchange("first", "one")
            memory.add_exchange("second", "two")
            self.assertEqual(len(memory.history), 2)
            self.assertEqual(memory.history[0]["parts"][0]["text"], "second")

    def test_invalid_file_starts_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            path.write_text("not json", encoding="utf-8")
            memory = ConversationMemory(path)
            self.assertEqual(memory.history, [])
            self.assertEqual(memory.facts, {})

    def test_migrates_legacy_history_list(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.json"
            path.write_text(json.dumps([
                {"role": "user", "parts": [{"text": "old"}]},
                {"role": "model", "parts": [{"text": "reply"}]},
            ]), encoding="utf-8")
            memory = ConversationMemory(path)
            self.assertEqual(len(memory.history), 2)
            self.assertEqual(memory.facts, {})


if __name__ == "__main__":
    unittest.main()
