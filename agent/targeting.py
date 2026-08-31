from __future__ import annotations

import re
from difflib import SequenceMatcher

from .core import Target, UIElement, element_text


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.lower()))


def _score(goal: str, element: UIElement) -> float:
    goal_tokens = _tokens(goal)
    label = element_text(element)
    label_tokens = _tokens(label)
    if not goal_tokens or not label_tokens:
        return 0.0
    overlap = len(goal_tokens & label_tokens) / len(goal_tokens)
    ratio = SequenceMatcher(None, goal.lower(), label.lower()).ratio()
    exact = 1.0 if goal.strip().lower() == label.strip().lower() else 0.0
    return exact * 10.0 + overlap * 4.0 + ratio


def find_target(goal: str, elements: tuple[UIElement, ...] | list[UIElement]) -> Target | None:
    candidates = [e for e in elements if e.enabled and e.clickable]
    if not candidates:
        return None
    ranked = sorted(candidates, key=lambda e: _score(goal, e), reverse=True)
    best = ranked[0]
    if _score(goal, best) <= 0:
        return None
    return Target(best.id, best.text, best.content_description)
