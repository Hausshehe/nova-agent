"""Mission-level runtime brain for Nova Agent v2."""

from __future__ import annotations

from dataclasses import dataclass, field

from .learning_memory import MissionLearningRecord
from .learning_policy import LearningAssessment
from .mission_state import MissionState
from .models import Decision, ExecutionResult, Goal, Observation, RunResult, RunStatus
from .planning import Plan
from .reasoning import ReasoningContext
from .run_controller import RunController
from .state_machine import RunState
from .working_memory import WorkingMemory


@dataclass
class RuntimeBrain:
    """Own the mission lifecycle, evidence-backed state, memory, and plan."""

    controller: RunController
    goal_verified: bool = False
    memory: WorkingMemory = field(init=False)
    mission: MissionState = field(init=False)
    plan: Plan | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.memory = WorkingMemory(goal=self.controller.goal)
        self.mission = MissionState(goal=self.controller.goal)

    @classmethod
    def create(cls, goal: Goal, max_steps: int = 20, max_memory_history: int = 6) -> "RuntimeBrain":
        brain = cls(RunController(goal=goal, max_steps=max_steps))
        brain.memory = WorkingMemory(goal=goal, max_history=max_memory_history)
        brain.mission = MissionState(goal=goal)
        return brain

    @property
    def state(self) -> RunState:
        return self.controller.state

    @property
    def goal(self) -> Goal:
        return self.controller.goal

    def start(self) -> None:
        self.controller.move(RunState.OBSERVING)

    def record_observation(self, observation: Observation) -> None:
        self.controller.record_observation(observation)
        self.memory.observe(observation)
        self.mission = self.mission.observed(observation)
        self.controller.move(RunState.DECIDING)

    def set_plan(self, plan: Plan) -> None:
        self.plan = plan

    def advance_plan(self) -> None:
        if self.plan is not None:
            self.plan = self.plan.advance()

    def reasoning_context(
        self,
        *,
        evidence: object | None = None,
        relevant_learning: tuple[MissionLearningRecord, ...] = (),
        learning_assessment: LearningAssessment | None = None,
    ) -> ReasoningContext:
        observation = self.memory.observation
        if self.state != RunState.DECIDING or observation is None:
            raise RuntimeError("reasoning context requires a current observation")
        return ReasoningContext(
            goal=self.goal,
            observation=observation,
            history=self.memory.history,
            evidence=evidence,
            mission_state=self.mission,
            plan=self.plan,
            relevant_learning=relevant_learning,
            learning_assessment=learning_assessment,
        )

    def record_decision(self, decision: Decision) -> None:
        self.controller.record_decision(decision)
        self.mission = self.mission.decided(decision)
        self.controller.move(RunState.EXECUTING)

    def record_execution(self, result: ExecutionResult) -> None:
        self.controller.record_execution(result)
        self.memory.remember_step(self.controller.history[-1])
        self.mission = self.mission.executed(result)
        self.controller.move(RunState.VERIFYING)

    def finish_verification(self, observation: Observation, *, goal_achieved: bool) -> RunResult | None:
        self.controller.record_post_observation(observation)
        self.memory.remember_post_observation(observation)
        self.mission = self.mission.verified(observation, goal_achieved)
        if goal_achieved:
            self.goal_verified = True
            return self.controller.finish(RunStatus.SUCCEEDED)
        self.controller.move(RunState.OBSERVING)
        return None

    def verify_post_observation(self, observation: Observation, *, goal_achieved: bool) -> RunResult | None:
        return self.finish_verification(observation, goal_achieved=goal_achieved)

    def record_post_observation(self, observation: Observation) -> None:
        self.finish_verification(observation, goal_achieved=False)

    def complete(self) -> RunResult:
        if self.state is not RunState.VERIFYING:
            raise RuntimeError("goal completion must be verified from the verifying state")
        if not self.controller.history or self.controller.history[-1].post_observation is None:
            raise RuntimeError("goal completion requires a verified post-observation")
        self.goal_verified = True
        self.mission = self.mission.verified(self.controller.history[-1].post_observation, True)
        return self.controller.finish(RunStatus.SUCCEEDED)

    def fail(self, error: str) -> RunResult:
        self.goal_verified = False
        self.mission = self.mission.verified(self.mission.observation, False) if self.mission.observation else self.mission
        return self.controller.finish(RunStatus.FAILED, error=error)

    def abort(self, error: str | None = None) -> RunResult:
        self.goal_verified = False
        self.mission = self.mission.verified(self.mission.observation, False) if self.mission.observation else self.mission
        return self.controller.finish(RunStatus.ABORTED, error=error)
