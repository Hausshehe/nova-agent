"""Local JSON-backed structured memory and recent conversation history."""

import json
from pathlib import Path


class ConversationMemory:
    def __init__(self, path: str | Path = "memory.json", max_messages: int = 40) -> None:
        self.path = Path(path)
        self.max_messages = max_messages
        self.facts: dict[str, str] = {}
        self.history: list[dict] = []
        self.load()

    def load(self) -> list[dict]:
        if not self.path.exists():
            return self.history
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self.history

        if isinstance(data, list):
            self.history = self._valid_history(data)[-self.max_messages:]
            self.facts = {}
        elif isinstance(data, dict):
            self.facts = {
                str(key): str(value)
                for key, value in data.get("facts", {}).items()
                if isinstance(key, str) and isinstance(value, (str, int, float, bool))
            }
            raw_history = data.get("history", [])
            self.history = self._valid_history(raw_history)[-self.max_messages:]
        else:
            self.facts = {}
            self.history = []
        return self.history

    @staticmethod
    def _valid_history(data: object) -> list[dict]:
        if not isinstance(data, list):
            return []
        return [
            item for item in data
            if isinstance(item, dict)
            and item.get("role") in {"user", "model"}
            and isinstance(item.get("parts"), list)
        ]

    @staticmethod
    def _normalize_key(key: str) -> str:
        return key.strip().lower().replace(" ", "_")

    def remember_fact(self, key: str, value: str) -> str:
        key = self._normalize_key(key)
        value = value.strip()
        if not key or not value:
            raise ValueError("Both fact key and value are required.")
        self.facts[key] = value
        self._save()
        return f"Remembered {key} = {value}"

    def forget_fact(self, key: str) -> str:
        key = self._normalize_key(key)
        if not key:
            raise ValueError("A fact key is required.")
        if key not in self.facts:
            return f"No remembered fact named {key}."
        del self.facts[key]
        self._save()
        return f"Forgot {key}."

    def context(self) -> list[dict]:
        if not self.facts:
            return list(self.history)
        facts = "\n".join(
            f"- {key}: {value}" for key, value in sorted(self.facts.items())
        )
        return [
            {
                "role": "user",
                "parts": [{"text": f"Durable memory about the user:\n{facts}"}],
            },
            *self.history,
        ]

    def add_exchange(self, prompt: str, answer: str) -> None:
        self.history.extend([
            {"role": "user", "parts": [{"text": prompt}]},
            {"role": "model", "parts": [{"text": answer}]},
        ])
        self.history = self.history[-self.max_messages:]
        self._save()

    def _save(self) -> None:
        data = {"facts": self.facts, "history": self.history}
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
