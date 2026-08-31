from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Protocol


class TaskStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NavigationExecutor(Protocol):
    """Task-level navigation capability.

    The runtime deliberately does not know how navigation works. This keeps
    task orchestration separate from observation, planning, and Android I/O.
    """

    def execute(self, goal: str) -> bool: ...


@dataclass(frozen=True)
class TaskEvent:
    kind: str
    message: str = ""


@dataclass(frozen=True)
class TaskResult:
    goal: str
    status: TaskStatus
    events: tuple[TaskEvent, ...] = ()
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.status is TaskStatus.COMPLETED


@dataclass
class TaskRuntime:
    """Owns the lifecycle of a user task, not the navigation algorithm.

    This is the first rebuild boundary. The existing NavigationLoop can be
    adapted behind NavigationExecutor while a new navigation engine is built
    without changing task-facing behavior.
    """

    navigation: NavigationExecutor
    on_event: Callable[[TaskEvent], None] | None = None
    _cancel_requested: bool = field(default=False, init=False, repr=False)

    def cancel(self) -> None:
        self._cancel_requested = True

    def run(self, goal: str) -> TaskResult:
        events: list[TaskEvent] = []

        def emit(kind: str, message: str = "") -> None:
            event = TaskEvent(kind=kind, message=message)
            events.append(event)
            if self.on_event is not None:
                self.on_event(event)

        if not goal.strip():
            emit("failed", "Goal is empty")
            return TaskResult(goal, TaskStatus.FAILED, tuple(events), "empty goal")

        if self._cancel_requested:
            emit("cancelled", "Task cancelled before execution")
            return TaskResult(goal, TaskStatus.CANCELLED, tuple(events))

        emit("started", goal)
        try:
            completed = self.navigation.execute(goal)
        except Exception as exc:  # Runtime boundary contains executor failures.
            error = f"{type(exc).__name__}: {exc}"
            emit("failed", error)
            return TaskResult(goal, TaskStatus.FAILED, tuple(events), error)

        if self._cancel_requested:
            emit("cancelled", "Task cancelled after execution")
            return TaskResult(goal, TaskStatus.CANCELLED, tuple(events))

        if completed:
            emit("completed", goal)
            return TaskResult(goal, TaskStatus.COMPLETED, tuple(events))

        emit("failed", "Navigation executor did not complete the goal")
        return TaskResult(
            goal,
            TaskStatus.FAILED,
            tuple(events),
            "navigation executor returned false",
        )


@dataclass(frozen=True)
class LegacyNavigationExecutor:
    """Compatibility adapter for the current NavigationLoop.

    It lets the new task runtime land without forcing a risky rewrite of the
    working Android bridge or deterministic navigation code in one step.
    """

    navigation_loop: object

    def execute(self, goal: str) -> bool:
        run = getattr(self.navigation_loop, "run", None)
        if not callable(run):
            raise TypeError("navigation_loop must expose callable run(goal)")
        return bool(run(goal))
