"""Bounded goal contracts for Nova's goal-driven autonomy phase."""

from __future__ import annotations

from dataclasses import dataclass


_MAX_TEXT = 512


@dataclass(frozen=True)
class GoalContract:
    """The explicit contract Nova must use to distinguish progress from completion."""

    goal: str
    success_condition: str
    status: str = "ACTIVE"

    def __post_init__(self) -> None:
        if not isinstance(self.goal, str) or not self.goal.strip():
            raise ValueError("Goal cannot be empty.")
        if not isinstance(self.success_condition, str) or not self.success_condition.strip():
            raise ValueError("Success condition cannot be empty.")
        if self.status not in {"ACTIVE", "VERIFIED", "FAILED"}:
            raise ValueError("Goal status must be ACTIVE, VERIFIED, or FAILED.")
        if len(self.goal.strip()) > _MAX_TEXT:
            raise ValueError("Goal is too long.")
        if len(self.success_condition.strip()) > _MAX_TEXT:
            raise ValueError("Success condition is too long.")

    def snapshot(self) -> dict[str, str]:
        return {
            "goal": self.goal.strip(),
            "success_condition": self.success_condition.strip(),
            "status": self.status,
        }


@dataclass(frozen=True)
class OutcomeContract:
    """Define the observable transition and evidence needed to prove a goal outcome."""

    goal: str
    success_condition: str
    expected_transition: str
    observable_evidence: str
    failure_condition: str
    uncertainty: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.goal, "Goal"),
            (self.success_condition, "Success condition"),
            (self.expected_transition, "Expected transition"),
            (self.observable_evidence, "Observable evidence"),
            (self.failure_condition, "Failure condition"),
            (self.uncertainty, "Uncertainty"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} cannot be empty.")
            if len(value.strip()) > _MAX_TEXT:
                raise ValueError(f"{label} is too long.")

    def snapshot(self) -> dict[str, str]:
        return {
            "goal": self.goal.strip(),
            "success_condition": self.success_condition.strip(),
            "expected_transition": self.expected_transition.strip(),
            "observable_evidence": self.observable_evidence.strip(),
            "failure_condition": self.failure_condition.strip(),
            "uncertainty": self.uncertainty.strip(),
        }


def establish_outcome_contract(
    goal: str,
    success_condition: str,
    expected_transition: str,
    observable_evidence: str,
    failure_condition: str,
    uncertainty: str,
) -> str:
    """Create a bounded outcome contract without executing or changing state."""
    contract = OutcomeContract(
        goal.strip(),
        success_condition.strip(),
        expected_transition.strip(),
        observable_evidence.strip(),
        failure_condition.strip(),
        uncertainty.strip(),
    )
    return (
        "Outcome contract established (read-only).\\n"
        f"Goal: {contract.goal.strip()}\\n"
        f"Success condition: {contract.success_condition.strip()}\\n"
        f"Expected transition: {contract.expected_transition.strip()}\\n"
        f"Observable evidence: {contract.observable_evidence.strip()}\\n"
        f"Failure condition: {contract.failure_condition.strip()}\\n"
        f"Uncertainty: {contract.uncertainty.strip()}\\n"
        "Safety boundary: this defines the intended outcome and its evidence only; "
        "no action was executed and no device state was changed."
    )



@dataclass(frozen=True)
class IntentContract:
    """Bounded representation of user intent without silently resolving material ambiguity."""

    request: str
    intended_goal: str
    desired_outcome: str
    explicit_constraints: str
    inferred_constraints: str
    required_evidence: str
    uncertainty: str
    assumptions: str
    clarification_required: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.request, "Request"),
            (self.intended_goal, "Intended goal"),
            (self.desired_outcome, "Desired outcome"),
            (self.explicit_constraints, "Explicit constraints"),
            (self.inferred_constraints, "Inferred constraints"),
            (self.required_evidence, "Required evidence"),
            (self.uncertainty, "Uncertainty"),
            (self.assumptions, "Assumptions"),
            (self.clarification_required, "Clarification requirement"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} cannot be empty.")
            if len(value.strip()) > 1024:
                raise ValueError(f"{label} is too long.")

    def snapshot(self) -> dict[str, str]:
        return {
            "request": self.request.strip(),
            "intended_goal": self.intended_goal.strip(),
            "desired_outcome": self.desired_outcome.strip(),
            "explicit_constraints": self.explicit_constraints.strip(),
            "inferred_constraints": self.inferred_constraints.strip(),
            "required_evidence": self.required_evidence.strip(),
            "uncertainty": self.uncertainty.strip(),
            "assumptions": self.assumptions.strip(),
            "clarification_required": self.clarification_required.strip(),
        }


def establish_intent_contract(request: str) -> str:
    """Transform raw user intent into a bounded contract without executing anything."""
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Request cannot be empty.")
    request = request.strip()
    if len(request) > 1024:
        raise ValueError("Request is too long.")

    lowered = request.lower()
    ambiguity_markers = (
        r"\b(?:this|that|it|the thing|something|whatever)\b",
        r"\b(?:fix|handle|open|do|make sure)\s+(?:this|that|it|the thing|whatever)\b",
        r"\bget me ready for\b",
        r"\bmake sure i (?:don't|do not) forget\b",
        r"\bi need this handled\b",
        r"\bdo whatever is necessary\b",
    )
    material_ambiguity = any(re.search(pattern, lowered) for pattern in ambiguity_markers)

    explicit = []
    for pattern in (
        r"\b(?:before|after|by)\s+[^,.!?;]+",
        r"\b(?:without|only)\s+[^,.!?;]+",
        r"\b(?:must|need to|do not|don't)\s+[^,.!?;]+",
    ):
        for match in re.finditer(pattern, request, re.IGNORECASE):
            value = match.group(0).strip()
            if value not in explicit:
                explicit.append(value)

    if material_ambiguity:
        intended_goal = request
        desired_outcome = "Unresolved: the requested target and/or concrete outcome is not explicit enough to verify safely."
        explicit_constraints = "; ".join(explicit) if explicit else "None stated explicitly."
        inferred_constraints = "Do not invent the missing target, outcome, or context; preserve the unresolved intent until clarified."
        required_evidence = "A concrete target and observable success condition must be established before execution."
        uncertainty = "Material ambiguity remains about what the user wants acted on or what result would count as success."
        assumptions = "None about the missing target or outcome."
        clarification = "REQUIRED"
    else:
        intended_goal = request
        desired_outcome = "The requested result is achieved and supported by observable evidence."
        explicit_constraints = "; ".join(explicit) if explicit else "None stated explicitly."
        inferred_constraints = "Do not add unstated user-specific constraints or silently broaden the request."
        required_evidence = "Evidence must support the requested result and any explicit constraints."
        uncertainty = "No material intent ambiguity detected from the supplied request."
        assumptions = "The request itself is the source of intent; no unsupported target or constraint was invented."
        clarification = "NOT REQUIRED"

    contract = IntentContract(
        request, intended_goal, desired_outcome, explicit_constraints,
        inferred_constraints, required_evidence, uncertainty, assumptions, clarification,
    )
    return "\n".join([
        "Intent contract established (read-only):",
        f"Request: {contract.request}",
        f"Intended goal: {contract.intended_goal}",
        f"Desired outcome: {contract.desired_outcome}",
        f"Explicit constraints: {contract.explicit_constraints}",
        f"Inferred constraints: {contract.inferred_constraints}",
        f"Required evidence: {contract.required_evidence}",
        f"Uncertainty: {contract.uncertainty}",
        f"Assumptions: {contract.assumptions}",
        f"Clarification requirement: {contract.clarification_required}",
        "Safety boundary: intent was interpreted without executing any capability or changing device state.",
    ])

def establish_goal_contract(goal: str, success_condition: str) -> str:
    """Create one bounded goal contract without executing or changing device state."""
    contract = GoalContract(goal.strip(), success_condition.strip())
    return (
        "Goal contract established.\n"
        f"Goal: {contract.goal.strip()}\n"
        f"Success condition: {contract.success_condition.strip()}\n"
        f"Status: {contract.status}\n"
        "Safety boundary: this records the goal and its completion condition only; "
        "no action was executed and no device state was changed."
    )
