from agent.agent_state import AgentState
from agent.core import WorldState
from agent.reasoning_context import build_reasoning_context


def test_agent_state_records_bounded_history_and_runtime_metadata():
    state = AgentState(goal="Finish task", world=WorldState(observation_id="0"), max_history=2)

    state = state.record({"step": 1, "action_type": "click"})
    state = state.record({"step": 2, "action_type": "click"}, failure=True, error="rejected")
    state = state.record(
        {"step": 3, "action_type": "wait"},
        world=WorldState(observation_id="3"),
        status="running",
        error=None,
        plan=("finish",),
    )

    assert state.step == 3
    assert state.world.observation_id == "3"
    assert state.failure_count == 1
    assert state.last_error is None
    assert state.plan == ("finish",)
    assert [item["step"] for item in state.history] == [2, 3]


def test_reasoning_context_exposes_same_working_state():
    state = AgentState(
        goal="Finish task",
        world=WorldState(observation_id="7"),
        step=3,
        status="running",
        failure_count=1,
        last_error="rejected",
        plan=("finish",),
    )

    context = build_reasoning_context(
        state.goal,
        state.world,
        state.history,
        agent_state=state,
    )

    assert context.agent_state is state
    assert context.agent_state.step == 3
    assert context.agent_state.status == "running"
    assert context.agent_state.failure_count == 1
    assert context.agent_state.last_error == "rejected"
    assert context.agent_state.plan == ("finish",)
