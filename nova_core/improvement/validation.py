"""Deterministic validation gates for candidate repairs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationPolicy:
    """Fixed validation commands and resource bounds controlled by Nova's policy."""

    commands: tuple[tuple[str, ...], ...] = (("python", "-m", "pytest", "-q"),)
    timeout_seconds: int = 60
    max_output_chars: int = 12_000

    def __post_init__(self) -> None:
        if not self.commands:
            raise ValueError("validation policy requires at least one command")
        if self.timeout_seconds <= 0:
            raise ValueError("validation timeout must be positive")
        if self.max_output_chars <= 0:
            raise ValueError("validation output limit must be positive")
        for command in self.commands:
            if not command or any(not part.strip() for part in command):
                raise ValueError("validation commands must be non-empty")
