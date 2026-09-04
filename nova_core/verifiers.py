"""Deterministic goal verification for Nova Agent v2."""

from __future__ import annotations

import re

from .models import ActionType, Decision, ExecutionResult, Goal, Observation


class VisibleTextVerifier:
    """Verify a goal when its normalized words are visible in the fresh UI."""

    def verify(
        self,
        goal: Goal,
        before: Observation,
        decision: Decision,
        result: ExecutionResult,
        after: Observation,
    ) -> bool:
        if not result.accepted or not result.changed:
            return False
        wanted = _tokens(goal.text)
        if not wanted:
            return False
        visible = _tokens(" ".join(
            [element.text for element in after.elements if element.visible]
            + [element.content_description for element in after.elements if element.visible]
        ))
        return all(token in visible for token in wanted)


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[\w]+", value.casefold())
        if token
    }
