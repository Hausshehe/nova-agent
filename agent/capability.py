"""Shared capability identifiers for Nova's AI routing layer."""

from __future__ import annotations

from enum import Enum


class Capability(str, Enum):
    REASONING = "reasoning"
    PERCEPTION = "perception"
    ACTION_SELECTION = "action_selection"
    VERIFICATION = "verification"
