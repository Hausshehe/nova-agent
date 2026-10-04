"""Local JSON-backed conversation history."""

import json
from pathlib import Path


class ConversationMemory:
    def __init__(self, path: str | Path = "memory.json", max_messages: int = 40) -> None:
        self.path = Path(path)
        self.max_messages = max_messages
        self.history = self.load()

    def load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return []
            return [
                item for item in data
                if isinstance(item, dict)
                and item.get("role") in {"user", "model"}
                and isinstance(item.get("parts"), list)
            ][-self.max_messages:]
        except (OSError, json.JSONDecodeError):
            return []

    def add_exchange(self, prompt: str, answer: str) -> None:
        self.history.extend([
            {"role": "user", "parts": [{"text": prompt}]},
            {"role": "model", "parts": [{"text": answer}]},
        ])
        self.history = self.history[-self.max_messages:]
        self.path.write_text(
            json.dumps(self.history, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
