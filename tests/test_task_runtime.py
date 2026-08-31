from dataclasses import dataclass

from agent.task_runtime import (
    LegacyNavigationExecutor,
    TaskRuntime,
    TaskStatus,
)


@dataclass
class FakeNavigation:
    result: bool = True
    calls: list[str] | None = None

    def __post_init__(self) -> None:
        if self.calls is None:
            self.calls = []

    def execute(self, goal: str) -> bool:
        self.calls.append(goal)
        return self.result


def test_runtime_rejects_empty_goal_without_calling_navigation() -> None:
    navigation = FakeNavigation()
    runtime = TaskRuntime(navigation)

    result = runtime.run("   ")

    assert result.status is TaskStatus.FAILED
    assert result.error == "empty goal"
    assert navigation.calls == []
    assert [event.kind for event in result.events] == ["failed"]


def test_runtime_completes_successful_task_and_emits_lifecycle_events() -> None:
    navigation = FakeNavigation(result=True)
    seen: list[str] = []
    runtime = TaskRuntime(navigation, on_event=lambda event: seen.append(event.kind))

    result = runtime.run("Tap Test Navigation Action")

    assert result.success
    assert result.status is TaskStatus.COMPLETED
    assert navigation.calls == ["Tap Test Navigation Action"]
    assert seen == ["started", "completed"]


def test_runtime_contains_executor_failure() -> None:
    class BrokenNavigation:
        def execute(self, goal: str) -> bool:
            raise RuntimeError("bridge exploded")

    result = TaskRuntime(BrokenNavigation()).run("Do something")

    assert result.status is TaskStatus.FAILED
    assert result.error == "RuntimeError: bridge exploded"
    assert result.events[-1].kind == "failed"


def test_legacy_adapter_preserves_navigation_loop_boundary() -> None:
    navigation = FakeNavigation(result=True)
    adapter = LegacyNavigationExecutor(navigation)

    assert adapter.execute("Open Settings") is True
    assert navigation.calls == ["Open Settings"]


def test_runtime_can_be_cancelled_before_execution() -> None:
    navigation = FakeNavigation()
    runtime = TaskRuntime(navigation)
    runtime.cancel()

    result = runtime.run("Open Settings")

    assert result.status is TaskStatus.CANCELLED
    assert navigation.calls == []
    assert result.events[-1].kind == "cancelled"
