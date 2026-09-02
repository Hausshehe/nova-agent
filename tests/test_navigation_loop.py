from dataclasses import dataclass

from agent.core import Action, ActionType, Decision, ExecutionResult, Target, UIElement, WorldState
from agent.deterministic_reasoner import DeterministicReasoner
from agent.navigation import NavigationLoop
from agent.reasoning_context import ReasoningContext


@dataclass
class FakeBridge:
    states: list[WorldState]
    accepted: bool = True
    changed: bool = True
    index: int = 0
    actions: list[Action] = None
    wait_calls: int = 0

    def __post_init__(self):
        self.actions = []

    def observe(self):
        return self.states[self.index]

    def execute(self, action):
        self.actions.append(action)
        return ExecutionResult(self.accepted, self.changed)

    def wait_for_fresh_observation(self, previous, timeout):
        self.wait_calls += 1
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


class DecideOnlyProvider:
    """Provider-shaped test double with no legacy plan() method."""

    def __init__(self):
        self.calls = 0
        self.contexts = []

    def decide(self, context: ReasoningContext):
        self.calls += 1
        self.contexts.append(context)
        element = context.state.elements[0]
        return Decision(
            Action(
                ActionType.CLICK,
                Target(element.id, element.text, element.content_description),
            ),
            "provider boundary",
        )


class FixedActionPlanner:
    def __init__(self, action_type):
        self.calls = 0
        self.action_type = action_type

    def plan(self, context):
        self.calls += 1
        return Decision(Action(self.action_type), "test global action")


class RecoveryPlanner:
    def __init__(self):
        self.calls = 0
        self.contexts = []
        self.reasoner = DeterministicReasoner()

    def plan(self, context):
        self.calls += 1
        self.contexts.append(context)
        return self.reasoner.plan(context)


class NoTransitionVerifier:
    def verify(self, before, after, result):
        return False


class FirstFailureThenSuccessVerifier:
    def __init__(self):
        self.calls = 0

    def verify(self, before, after, result):
        self.calls += 1
        return self.calls >= 2 and result.accepted and result.changed


def test_navigation_loop_completes_after_observation_transition():
    button = UIElement("n1", text="Finish", clickable=True)
    before = WorldState(package="nova", observation_id="1", elements=(button,))
    after = WorldState(package="nova", observation_id="2", elements=(UIElement("n2", text="Navigation Complete"),))
    bridge = FakeBridge([before, after])

    assert NavigationLoop(bridge, SequencePlanner(), max_steps=2).run("Navigation Complete") is True
    assert len(bridge.actions) == 1


def test_navigation_loop_accepts_decide_only_reasoning_provider():
    button = UIElement("n1", text="Finish", clickable=True)
    before = WorldState(package="nova", observation_id="1", elements=(button,))
    after = WorldState(package="nova", observation_id="2", elements=(UIElement("n2", text="Done"),))
    bridge = FakeBridge([before, after])
    provider = DecideOnlyProvider()

    assert NavigationLoop(bridge, provider, max_steps=1).run("Tap Finish") is True
    assert provider.calls == 1
    assert provider.contexts[0].goal == "Tap Finish"
    assert bridge.actions == [Action(ActionType.CLICK, Target("n1", "Finish", ""))]


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


def test_navigation_loop_replans_to_alternative_after_unverified_action():
    first = UIElement("n1", text="Complete", clickable=True)
    fallback = UIElement("n2", text="task", clickable=True)
    before = WorldState(package="nova", observation_id="1", elements=(first, fallback))
    after_first = WorldState(package="nova", observation_id="2", elements=(first, fallback))
    after_second = WorldState(package="nova", observation_id="3", elements=(UIElement("n3", text="Complete task"),))
    bridge = FakeBridge([before, after_first, after_second])
    planner = RecoveryPlanner()
    verifier = FirstFailureThenSuccessVerifier()

    assert NavigationLoop(bridge, planner, verifier=verifier, max_steps=2).run("Complete task") is True
    assert planner.calls == 2
    assert len(bridge.actions) == 2
    assert bridge.actions[0].target.element_id == "n1"
    assert bridge.actions[1].target.element_id == "n2"
    assert planner.contexts[1].history[0]["target_id"] == "n1"
    assert planner.contexts[1].history[0]["verified"] is False


def test_action_goal_requires_an_executed_and_verified_action():
    button = UIElement("n1", text="Test Navigation Action", clickable=True)
    before = WorldState(package="nova", observation_id="1", elements=(button,))
    after = WorldState(package="nova", observation_id="2", elements=(UIElement("n2", text="Navigation Action Completed"),))
    bridge = FakeBridge([before, after])

    assert NavigationLoop(bridge, SequencePlanner(), max_steps=1).run("Tap Test Navigation Action") is True
    assert len(bridge.actions) == 1


def test_navigation_loop_executes_back_action_and_verifies_transition():
    before = WorldState(package="nova", activity="Details", observation_id="1")
    after = WorldState(package="nova", activity="Home", observation_id="2")
    bridge = FakeBridge([before, after])
    planner = FixedActionPlanner(ActionType.BACK)

    assert NavigationLoop(bridge, planner, max_steps=1).run("Go back") is True
    assert planner.calls == 1
    assert bridge.actions == [Action(ActionType.BACK)]


def test_navigation_loop_wait_goal_completes_without_state_change():
    state = WorldState(package="nova", activity="Ready", observation_id="1")
    bridge = FakeBridge([state])
    planner = FixedActionPlanner(ActionType.WAIT)

    assert NavigationLoop(bridge, planner, max_steps=1).run("Wait") is True
    assert planner.calls == 1
    assert bridge.actions == []
    assert bridge.wait_calls == 0


def test_navigation_loop_waits_for_fresh_observation_without_bridge_command():
    before = WorldState(package="nova", activity="Loading", observation_id="1")
    after = WorldState(package="nova", activity="Ready", observation_id="2")
    bridge = FakeBridge([before, after])
    planner = FixedActionPlanner(ActionType.WAIT)

    assert NavigationLoop(bridge, planner, max_steps=1).run("Wait") is True
    assert planner.calls == 1
    assert bridge.actions == []
    assert bridge.wait_calls == 0
