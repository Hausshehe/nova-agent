from dataclasses import dataclass

from agent.core import Action, ActionType, Decision, ExecutionResult, UIElement, WorldState
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

    def plan(self, context):
        self.calls += 1
        return Decision(
            Action(ActionType.CLICK, context.state.elements[0] and __import__("agent.core", fromlist=["Target"]).Target(
                context.state.elements[0].id,
                context.state.elements[0].text,
                context.state.elements[0].content_description,
            )),
            "test sequence",
        )


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
