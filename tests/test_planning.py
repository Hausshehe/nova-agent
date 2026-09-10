import pytest

from nova_core.models import Goal, Observation, UiElement
from nova_core.planning import GoalPlanner, Plan, PlanStep
from nova_core.reasoning import ReasoningContext


def _context() -> ReasoningContext:
    return ReasoningContext(
        goal=Goal("Finish the task"),
        observation=Observation(
            package="com.example.app",
            activity="MainActivity",
            revision=1,
            elements=(UiElement(id="button", text="Continue", clickable=True),),
        ),
    )


def test_plan_is_bounded_and_advances_without_mutation():
    plan = Plan(tuple(PlanStep(f"step {i}") for i in range(8)))
    advanced = plan.advance()

    assert len(plan.steps) == 8
    assert plan.cursor == 0
    assert advanced.cursor == 1
    assert advanced.current == PlanStep("step 1")
    assert plan.current == PlanStep("step 0")


def test_plan_rejects_empty_or_overlarge_sequences():
    with pytest.raises(ValueError, match="at least one"):
        Plan(())
    with pytest.raises(ValueError, match="at most 8"):
        Plan(tuple(PlanStep(str(i)) for i in range(9)))


def test_plan_progress_snapshot_explicitly_separates_completed_current_and_remaining():
    plan = Plan(
        (PlanStep("open settings"), PlanStep("enable Wi-Fi"), PlanStep("verify connection")),
        cursor=1,
    )

    assert plan.progress_snapshot == {
        "status": "in_progress",
        "completed": ["open settings"],
        "current": "enable Wi-Fi",
        "remaining": ["enable Wi-Fi", "verify connection"],
        "cursor": 1,
        "total": 3,
        "revision": 0,
    }


def test_completed_plan_progress_snapshot_has_no_current_or_remaining_intent():
    plan = Plan((PlanStep("finish"),), cursor=1)

    assert plan.progress_snapshot == {
        "status": "complete",
        "completed": ["finish"],
        "current": None,
        "remaining": [],
        "cursor": 1,
        "total": 1,
        "revision": 0,
    }


def test_goal_planner_creates_one_intent_without_inventing_actions():
    plan = GoalPlanner().plan(_context())

    assert plan.steps == (PlanStep("Finish the task"),)
    assert plan.current == PlanStep("Finish the task")
    assert plan.complete is False


def test_goal_planner_replans_with_new_revision():
    planner = GoalPlanner()
    previous = planner.plan(_context())
    replacement = planner.replan(_context(), previous)

    assert replacement.revision == 1
    assert replacement.cursor == 0
    assert replacement.steps == previous.steps
