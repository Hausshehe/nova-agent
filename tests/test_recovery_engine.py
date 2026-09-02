from agent.core import Action, ActionType, Decision, UIElement, WorldState
from agent.recovery_engine import RecoveryEngine
from agent.reasoning_context import build_reasoning_context


class RecoveryPlanner:
    def __init__(self):
        self.calls = 0
        self.contexts = []

    def decide(self, context):
        self.calls += 1
        self.contexts.append(context)
        target = context.candidates[-3].target
        return Decision(Action(ActionType.CLICK, target), "recovery decision")


def test_recovery_engine_replans_from_fresh_state_and_history():
    first = UIElement("n1", text="Wrong Action", clickable=True)
    fallback = UIElement("n2", text="Retry", clickable=True)
    state = WorldState(package="nova", observation_id="2", elements=(first, fallback))
    history = ({
        "step": 1,
        "action_type": "click",
        "target_id": "n1",
        "target_text": "Wrong Action",
        "accepted": False,
        "changed": False,
        "verified": False,
        "error": "rejected",
    },)
    planner = RecoveryPlanner()
    engine = RecoveryEngine()

    decision = engine.recover("Retry action", state, history, planner)

    assert engine.recoveries == 1
    assert planner.calls == 1
    assert planner.contexts[0].state is state
    assert planner.contexts[0].history == history
    assert decision.action.type is ActionType.CLICK


def test_recovery_engine_resets_between_tasks():
    engine = RecoveryEngine()
    planner = RecoveryPlanner()
    state = WorldState(observation_id="1", elements=(UIElement("n1", text="Retry", clickable=True),))

    engine.recover("Retry", state, (), planner)
    assert engine.recoveries == 1

    engine.reset()
    assert engine.recoveries == 0
