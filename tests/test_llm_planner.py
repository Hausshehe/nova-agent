import pytest

from nova_core.evidence import StateEvidence
from nova_core.llm_planner import LLMPlanner
from nova_core.models import Goal, Observation, UiElement
from nova_core.reasoning import ReasoningContext


def _context() -> ReasoningContext:
    return ReasoningContext(
        goal=Goal("Finish the task"),
        observation=Observation(
            package="com.example.app",
            activity="MainActivity",
            revision=3,
            elements=(
                UiElement(id="continue", text="Continue", clickable=True),
            ),
        ),
        evidence="evidence",
    )


def test_llm_planner_parses_bounded_intents_and_never_creates_actions():
    prompts = []

    def complete(prompt: str) -> str:
        prompts.append(prompt)
        return '{"steps":["start the task","continue until the target state"]}'

    plan = LLMPlanner(complete).plan(_context())

    assert [step.description for step in plan.steps] == [
        "start the task",
        "continue until the target state",
    ]
    assert plan.revision == 0
    assert "not UI actions" in prompts[0]
    assert "Finish the task" in prompts[0]
    assert '"revision":3' in prompts[0]


def test_llm_planner_replan_increments_revision_and_includes_previous_plan():
    prompts = []
    responses = iter(
        (
            '{"steps":["start the task","continue until the target state"]}',
            '{"steps":["recover from the blocked state"]}',
        )
    )

    def complete(prompt: str) -> str:
        prompts.append(prompt)
        return next(responses)

    planner = LLMPlanner(complete)
    previous = planner.plan(_context())
    replacement = planner.replan(_context(), previous)

    assert replacement.revision == 1
    assert replacement.steps[0].description == "recover from the blocked state"
    assert '"start the task"' in prompts[1]
    assert '"continue until the target state"' in prompts[1]


def test_llm_planner_rejects_non_json_and_malformed_shapes():
    for response in (
        "not json",
        '{"steps":[]}',
        '{"steps":["ok", 3]}',
        '{"steps":["ok"],"extra":"nope"}',
    ):
        with pytest.raises(ValueError):
            LLMPlanner(lambda _prompt, response=response: response).plan(_context())


def test_llm_planner_rejects_overlarge_response():
    response = '{"steps":[' + ','.join('"step"' for _ in range(9)) + ']}'

    with pytest.raises(ValueError, match="more than 8"):
        LLMPlanner(lambda _prompt: response).plan(_context())


def test_llm_planner_replan_preserves_recovery_intent_after_ineffective_action():
    context = _context()
    context = ReasoningContext(
        goal=context.goal,
        observation=Observation(
            package="com.example.app",
            activity="MainActivity",
            revision=4,
            elements=(
                UiElement(id="primary", text="Recovery Primary Action", clickable=True),
                UiElement(id="fallback", text="Recovery Fallback Action", clickable=True),
            ),
        ),
        evidence=StateEvidence(
            current_revision=4,
            previous_revision=3,
            last_execution_accepted=True,
            last_execution_changed=False,
        ),
    )
    planner = LLMPlanner(lambda _prompt: '{"steps":["Complete Recovery with Recovery Fallback Action"]}')
    replacement = planner.replan(context, planner.plan(_context()))
    assert replacement.steps[0].description == "Complete Recovery with Recovery Fallback Action"
