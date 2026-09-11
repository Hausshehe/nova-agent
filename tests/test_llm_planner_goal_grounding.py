from nova_core.llm_planner import LLMPlanner
from nova_core.models import Goal, Observation, UiElement
from nova_core.reasoning import ReasoningContext


class StubResponder:
    def __init__(self, response):
        self.response = response
        self.prompts = []

    def complete(self, prompt):
        self.prompts.append(prompt)
        return self.response


def _context():
    return ReasoningContext(
        goal=Goal("Finish Multi-Step Test"),
        observation=Observation(
            package="com.hausshehe.nova",
            activity="MainActivity",
            revision=1,
            elements=(
                UiElement(id="navigation", text="TEST NAVIGATION ACTION", clickable=True),
                UiElement(id="multi", text="MULTI-STEP TEST", clickable=True),
                UiElement(id="recovery", text="RECOVERY TEST", clickable=True),
            ),
        ),
    )


def test_planner_grounds_unrelated_first_intent_in_goal_relevant_current_ui():
    responder = StubResponder('{"steps":["Click TEST NAVIGATION ACTION","Click CONTINUE MULTI-STEP","Click FINISH MULTI-STEP"]}')
    planner = LLMPlanner(responder)

    plan = planner.plan(_context())

    assert plan.steps[0].description == "MULTI-STEP TEST"
    assert "TEST NAVIGATION ACTION" in responder.prompts[0]
    assert '"MULTI-STEP TEST"' in responder.prompts[0]


def test_planner_preserves_goal_relevant_first_intent():
    responder = StubResponder('{"steps":["Click MULTI-STEP TEST","Click CONTINUE MULTI-STEP","Click FINISH MULTI-STEP"]}')
    planner = LLMPlanner(responder)

    plan = planner.plan(_context())

    assert [step.description for step in plan.steps] == [
        "Click MULTI-STEP TEST",
        "Click CONTINUE MULTI-STEP",
        "Click FINISH MULTI-STEP",
    ]
