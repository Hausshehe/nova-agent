from dataclasses import dataclass

from agent.core import Action, ActionType, Decision, ExecutionResult, Target, UIElement, WorldState
from agent.navigation import NavigationLoop


@dataclass
class FakeBridge:
    states: list[WorldState]
    accepted: bool = True
    changed: bool = True
    index: int = 0
    actions: list[Action] = None

    def __post_init__(self):
        self.actions = []

    def observe(self):
        return self.states[self.index]

    def execute(self, action):
        self.actions.append(action)
        return ExecutionResult(self.accepted, self.changed)

    def wait_for_fresh_observation(self, previous, timeout):
        if self.index + 1 >= len(self.states):
            raise TimeoutError("no next state")
        self.index += 1
        return self.states[self.index]


class SequencePlanner:
    def __init__(self):
        self.calls = 0
        self.contexts = []

    def plan(self, context):
        self.calls += 1
        self.contexts.append(context)
        element = context.state.elements[0]
        return Decision(
            Action(
                ActionType.CLICK,
                Target(element.id, element.text, element.content_description),
            ),
            "test sequence",
        )


class NoTransitionVerifier:
    def verify(self, before, after, result):
        return False


def test_navigation_loop_completes_after_observation_transition():
    button = UIElement("n1", text="Finish", clickable=True)
    before = WorldState(package="nova", observation_id="1", elements=(button,))
    after = WorldState(package="nova", observation_id="2", elements=(UIElement("n2", text="Navigation Complete"),))
    bridge = FakeBridge([before, after])

    assert NavigationLoop(bridge, SequencePlanner(), max_steps=2).run("Navigation Complete") is True
    assert len(bridge.actions) == 1


def test_navigation_loop_stops_at_step_limit():
    button = UIElement("n1", text="Keep going", clickable=True)
    states = [WorldState(package="nova", observation_id=str(i), elements=(button,)) for i in range(4)]
    bridge = FakeBridge(states)
    planner = SequencePlanner()

    assert NavigationLoop(bridge, planner, max_steps=2).run("Something else") is False
    assert planner.calls == 2


def test_navigation_loop_replans_after_timeout():
    button = UIElement("n1", text="Keep going", clickable=True)
    state = WorldState(package="nova", observation_id="1", elements=(button,))
    bridge = FakeBridge([state, state])
    bridge.changed = False
    planner = SequencePlanner()

    assert NavigationLoop(bridge, planner, max_steps=2).run("Something else") is False
    assert planner.calls == 2


def test_navigation_history_records_unverified_action_for_replanning():
    first = UIElement("n1", text="Try action", clickable=True)
    second = UIElement("n2", text="Alternative action", clickable=True)
    before = WorldState(package="nova", observation_id="1", elements=(first, second))
    after = WorldState(package="nova", observation_id="2", elements=(first, second))
    bridge = FakeBridge([before, after])
    planner = SequencePlanner()

    assert NavigationLoop(bridge, planner, verifier=NoTransitionVerifier(), max_steps=2).run("Complete task") is False

    assert len(planner.contexts) == 2
    history = planner.contexts[1].history
    assert len(history) == 1
    attempt = history[0]
    assert attempt["step"] == 1
    assert attempt["action_type"] == "click"
    assert attempt["target_id"] == "n1"
    assert attempt["target_text"] == "Try action"
    assert attempt["accepted"] is True
    assert attempt["changed"] is True
    assert attempt["verified"] is False
    assert attempt["error"] is None
