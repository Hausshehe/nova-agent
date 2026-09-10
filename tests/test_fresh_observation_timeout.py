from dataclasses import dataclass

import pytest

from agent.android_bridge import AndroidBridge
from agent.core import UIElement, WorldState
from nova_core.adapters.android import AndroidBridgeAdapter
from nova_core.models import Action, ActionType, Decision, ExecutionResult, Goal
from nova_core.reasoning import ReasoningStep
from nova_core.run_controller import RunController
from nova_core.state_machine import RunState


@dataclass
class TimeoutBridge:
    state: WorldState

    def observe(self) -> WorldState:
        return self.state

    def wait_for_fresh_observation(self, previous, timeout=2.0, poll_seconds=0.2):
        raise TimeoutError("no observable change")


def _state(label: str = "Continue") -> WorldState:
    return WorldState(
        package="com.hausshehe.nova",
        activity=".MainActivity",
        elements=(
            UIElement(
                id="button",
                text=label,
                clickable=True,
                enabled=True,
            ),
        ),
        observation_id="same",
    )


def test_fresh_observation_timeout_returns_latest_ui(monkeypatch):
    clock = {"now": 0.0}

    def monotonic():
        return clock["now"]

    def sleep(seconds):
        clock["now"] += seconds

    monkeypatch.setattr("nova_core.adapters.android.time.monotonic", monotonic)
    monkeypatch.setattr("nova_core.adapters.android.time.sleep", sleep)

    bridge = TimeoutBridge(_state())
    adapter = AndroidBridgeAdapter(bridge=bridge, expected_package="com.hausshehe.nova")
    adapter.observe()

    fresh = adapter.observe_fresh(adapter.observe())

    assert fresh.package == "com.hausshehe.nova"
    assert fresh.elements[0].text == "Continue"


def test_controller_reconciliation_removes_optimistic_step_progress():
    controller = RunController(Goal("Finish"), max_steps=3)
    controller.state = RunState.EXECUTING
    decision = Decision(Action(ActionType.TAP, target_id="button"))
    controller.decision = decision
    controller.record_execution(ExecutionResult(accepted=True, changed=True))

    assert controller.steps == 1
    assert controller.history[-1].execution.changed is True

    controller.move(RunState.VERIFYING)
    controller.reconcile_execution(ExecutionResult(accepted=True, changed=False))

    assert controller.steps == 0
    assert controller.last_execution == ExecutionResult(accepted=True, changed=False)
    assert controller.history[-1].execution.changed is False
