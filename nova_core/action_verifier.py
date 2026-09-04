"""Verification for explicit action goals in Nova Agent v2."""

from __future__ import annotations

import re

from .models import Decision, ExecutionResult, Goal, Observation


_ACTION_VERBS = {"tap", "click", "back", "scroll", "type", "swipe", "wait"}


class ActionExecutionVerifier:
    """Verify an explicit action goal from accepted execution and fresh state.

    This verifier is intentionally scoped to goals whose first token is an
    explicit action verb. For such a goal, successful execution plus a fresh,
    changed observation is the strongest generic evidence available without
    inventing app-specific semantics.
    """

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
        if before == after:
            return False
        return _is_explicit_action_goal(goal.text)


def _is_explicit_action_goal(text: str) -> bool:
    match = re.match(r"^\s*([\w]+)\b", text.casefold())
    return bool(match and match.group(1) in _ACTION_VERBS)
