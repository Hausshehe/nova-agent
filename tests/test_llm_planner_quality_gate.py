from nova_core.llm_planner import LLMPlanner
from nova_core.models import Goal, Observation
from nova_core.reasoning import ReasoningContext


def _context() -> ReasoningContext:
    return ReasoningContext(
        goal=Goal("Finish the task"),
        observation=Observation("com.example.app", "MainActivity"),
    )


def test_llm_planner_rejects_meta_control_flow_intents():
    planner = LLMPlanner(lambda _: '{"steps":["Click the continue button","check if progress made"]}')

    try:
        planner.plan(_context())
    except ValueError as exc:
        assert "meta/control-flow intent" in str(exc)
    else:
        raise AssertionError("planner must reject meta/control-flow intents")


def test_llm_planner_rejects_duplicate_consecutive_intents():
    planner = LLMPlanner(lambda _: '{"steps":["Open settings","open settings"]}')

    try:
        planner.plan(_context())
    except ValueError as exc:
        assert "duplicate consecutive intent" in str(exc)
    else:
        raise AssertionError("planner must reject duplicate consecutive intents")


def test_llm_planner_normalizes_valid_intent_whitespace():
    planner = LLMPlanner(lambda _: '{"steps":["  Open   settings  ","Select account"]}')

    plan = planner.plan(_context())

    assert [step.description for step in plan.steps] == ["Open settings", "Select account"]
