from __future__ import annotations

import unittest

from .core import Action, ActionType, Decision, Target, UIElement, WorldState
from .runtime_brain import RuntimeBrain, RuntimeBrainConfig


class FakeBridge:
    def __init__(self) -> None:
        self.state = WorldState(
            package="com.example",
            activity="Main",
            elements=(UIElement("go", "Go", clickable=True),),
            observation_id="0",
        )
        self.counter = 0

    def observe(self) -> WorldState:
        return self.state

    def execute(self, action: Action):
        if action.type is not ActionType.CLICK or action.target is None:
            raise AssertionError("unexpected action")
        self.counter += 1
        self.state = WorldState(
            package=self.state.package,
            activity=self.state.activity,
            elements=(UIElement("done", "Done"),),
            observation_id=str(self.counter),
        )
        from .core import ExecutionResult
        return ExecutionResult(True, True)

    def wait_for_fresh_observation(self, previous: WorldState, timeout: float) -> WorldState:
        return self.state


class FailingProvider:
    def decide(self, context):
        raise RuntimeError("temporary provider outage")


class SuccessfulProvider:
    def decide(self, context):
        return Decision(Action(ActionType.CLICK, Target("go", "Go")), "test")


class RuntimeBrainTests(unittest.TestCase):
    def test_failover_keeps_navigation_kernel_bounded(self):
        brain = RuntimeBrain(
            FakeBridge(),
            [FailingProvider(), SuccessfulProvider()],
            config=RuntimeBrainConfig(max_steps=1, provider_attempts=1),
        )
        result = brain.run("tap Go")

        self.assertTrue(result.succeeded)
        self.assertIsNone(result.error)
        self.assertTrue(any(event.detail == "provider failed" for event in result.events))
        self.assertTrue(any(event.detail == "provider decision accepted" for event in result.events))
        self.assertEqual(result.events[-1].phase, "complete")

    def test_empty_goal_is_rejected_before_observation(self):
        brain = RuntimeBrain(FakeBridge(), [SuccessfulProvider()])
        result = brain.run("   ")

        self.assertFalse(result.succeeded)
        self.assertEqual(result.error, "goal must not be empty")
        self.assertEqual(result.events[1].phase, "stop")


if __name__ == "__main__":
    unittest.main()
