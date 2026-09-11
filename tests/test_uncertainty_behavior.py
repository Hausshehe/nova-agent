import json

from nova_core.llm_planner import LLMPlanner
from nova_core.models import Goal, Observation
from nova_core.reasoning import ReasoningContext
from nova_core.uncertainty import UncertaintyAssessment


def _context(uncertainty: UncertaintyAssessment) -> ReasoningContext:
    return ReasoningContext(
        goal=Goal("Finish the task"),
        observation=Observation(package="com.example", activity="MainActivity"),
        uncertainty=uncertainty,
    )


def test_high_uncertainty_is_explicit_behavioral_guidance():
    prompts: list[str] = []
    planner = LLMPlanner(lambda prompt: prompts.append(prompt) or json.dumps({"steps": ["Inspect the current task state"]}))

    planner.plan(_context(UncertaintyAssessment(
        level="high",
        basis="accepted action produced no observable change",
        unknowns=("whether the action advanced the goal",),
    )))

    prompt = prompts[0]
    assert '"level":"high"' in prompt
    assert '"mode":"reassess"' in prompt
    assert "resolves an unknown" in prompt
    assert "do not repeat an ineffective action without new evidence" in prompt


def test_medium_uncertainty_requires_verifiable_progress_guidance():
    prompts: list[str] = []
    planner = LLMPlanner(lambda prompt: prompts.append(prompt) or json.dumps({"steps": ["Continue the task"]}))

    planner.plan(_context(UncertaintyAssessment(
        level="medium",
        basis="action changed the UI",
        unknowns=("whether the change advances the goal",),
    )))

    prompt = prompts[0]
    assert '"level":"medium"' in prompt
    assert '"mode":"progress_check"' in prompt
    assert "effect can be verified from a fresh observation" in prompt


def test_low_uncertainty_keeps_normal_execution_mode():
    prompts: list[str] = []
    planner = LLMPlanner(lambda prompt: prompts.append(prompt) or json.dumps({"steps": ["Finish the task"]}))

    planner.plan(_context(UncertaintyAssessment(
        level="low",
        basis="goal completion verified",
    )))

    prompt = prompts[0]
    assert '"level":"low"' in prompt
    assert '"mode":"execute"' in prompt


def test_conflicting_evidence_is_not_silently_ignored():
    prompts: list[str] = []
    planner = LLMPlanner(lambda prompt: prompts.append(prompt) or json.dumps({"steps": ["Resolve the conflicting task state"]}))

    planner.plan(_context(UncertaintyAssessment(
        level="high",
        basis="current and historical evidence disagree",
        conflicts=("completion state conflicts with the current UI",),
    )))

    prompt = prompts[0]
    assert "Conflicting evidence must remain unresolved" in prompt
    assert "completion state conflicts with the current UI" in prompt
