# Nova Rebuild Architecture Reconnaissance

## Status

This document records the architectural reconnaissance for the Nova rebuild. It is deliberately a design document, not a code transplant.

## Strategic decision

Nova will stop treating the existing `NavigationLoop` as the long-term navigation architecture. The existing implementation is a verified prototype and regression baseline, but its central loop remains a tightly coupled deterministic planner/executor/verifier cycle.

The rebuild will use the architecture of the reference PrivateAgent project as the navigation design reference, while retaining Nova's Android bridge, accessibility integration, goal evaluation, testing discipline, and reliability requirements.

Reference project: `orailnoor/private-agent`

## Reference architecture discovered

The reference project is organized around a task executor and service boundaries rather than Nova's current `NavigationLoop` abstraction.

Important components observed:

- `TaskExecutor`: owns the high-level task lifecycle and repeated observe -> reason -> act cycle.
- `AiService`: provides the reasoning/model boundary.
- `ScreenAutomationService`: owns the native Accessibility bridge, screen dumps, screenshots, coordinates, and interaction primitives.
- `AppLauncherService`: app-launch capability.
- `RecoveryEngine`: explicit failure diagnosis and recovery action selection.
- `SkillMemoryService`: reusable successful task knowledge.
- `TaskHistoryLogger`: operational history.
- `ShizukuService`: optional privileged/device capabilities.

The reference README describes the core feedback loop as:

`goal -> screen hierarchy -> model decision -> native action -> fresh screen -> repeat until complete`

## What is architecturally valuable

### 1. A task executor owns the long-running task

Instead of making the navigation kernel itself responsible for the entire task, the task executor coordinates the lifecycle.

Nova should move toward:

`Goal -> Task State -> Observe -> Reason -> Action -> Observe -> Evaluate -> Complete/Replan`

The task lifecycle should be distinct from individual Android actions.

### 2. Observation is a first-class service

The reference implementation treats screen reading as a dedicated capability. Its screen service can expose:

- accessibility tree data
- current package
- element text/content description
- clickability/editability/scrollability
- bounds and centers
- screenshots
- interaction primitives

Nova already has much of this capability. It should be preserved and strengthened rather than rebuilt unnecessarily.

### 3. The model reasons over fresh screen state

The reference architecture gives the reasoning layer the current task, current screen representation, and previous action context, then asks for one next action.

This is closer to the long-term Nova design than the current deterministic target scorer.

### 4. Actions are capability-level operations

The reference action vocabulary includes operations such as:

- click by text
- click by coordinates
- type text
- submit/enter
- scroll
- swipe
- back
- home
- open app
- wait
- done

Nova should expose a controlled action interface rather than allowing the reasoning layer to manipulate Android implementation details directly.

### 5. Recovery is separated from normal execution

The reference project has a dedicated `RecoveryEngine` that diagnoses failures and selects an alternate action.

Nova should preserve this separation. Recovery should not become dozens of special cases inside the main navigation loop.

### 6. Memory is outside the navigation primitive

The reference project separates skill memory and task history from the core execution service.

Nova should eventually do the same:

- working task history
- successful skill memory
- failure history
- app-specific knowledge

Memory should be evidence, not unquestionable truth.

## Important differences and lessons

The reference project is not perfect and should not be copied blindly.

Observed weaknesses include explicit fixed delays and heuristic recovery rules. Nova's existing bounded transition-settling work is stronger and should be retained.

The reference implementation also contains application-specific shortcuts and fallback behavior. Nova should avoid turning those into a new hard-coded navigation system.

The goal is to adopt the architecture, not reproduce every implementation detail.

## Nova -> rebuilt architecture mapping

| Current Nova | Rebuild direction |
|---|---|
| `NavigationLoop` | Replace as the long-term orchestration abstraction with a task executor/agent loop |
| `WorldState` | Retain concept, expand into richer observation/task state |
| `NavigationBridge` | Evolve into Android capability boundary |
| `DeterministicReasoner` | Keep as baseline/fallback planner, not the ultimate brain |
| `GoalEvaluator` | Retain and make goal completion a hard termination condition |
| `TransitionVerifier` | Retain bounded state-transition verification |
| `targeting.py` | Retain useful matching primitives, but do not let fuzzy matching become the entire planner |
| `reasoning_context.py` | Evolve into structured task/observation context |
| `android_bridge.py` | Preserve as the Android/Termux communication boundary |
| recovery logic | Move toward a dedicated recovery subsystem |
| smoke tests | Preserve as regression gates and expand around the new architecture |

## Target architecture

```text
User Goal
   |
   v
Task / Goal Model
   |
   v
Task Executor / Agent Runtime
   |
   +--------------------+
   |                    |
   v                    v
Observation         Working Memory
   |
   v
Reasoner / Planner
   |
   v
Structured Action
   |
   v
Action Executor
   |
   v
Android Capability Boundary
   |
   v
Accessibility / Android
   |
   v
Fresh Observation
   |
   v
Goal Evaluator + Transition Verification
   |
   +----------+----------+
              |          |
           complete    failure
              |          |
              v          v
            DONE      Recovery / Replan
                           |
                           +----> Observation
```

## Migration principles

1. Do not delete working Android capabilities merely because the architecture changes.
2. Do not copy reference-project code wholesale without checking compatibility and licensing.
3. Keep the current deterministic planner as a regression/fallback asset until the new path proves itself.
4. Replace orchestration before replacing low-level Android capabilities.
5. Keep goal completion independent from action acceptance.
6. Keep bounded observation/transition settling from the current Nova implementation.
7. Test every migration layer independently and then on the real phone.
8. Do not add an LLM until the new task/navigation boundary is stable enough to accept one.

## Immediate implementation order

### R0 — Reconnaissance

Complete architecture mapping and baseline preservation.

### R1 — New task runtime skeleton

Introduce a task-executor boundary without changing Android behavior.

### R2 — Observation boundary

Adapt Nova's existing Android observation into the new task runtime.

### R3 — Action boundary

Adapt existing click/back/wait/other actions into a capability-level interface.

### R4 — Goal verification

Make completion evaluation independent of whether an action was accepted.

### R5 — Recovery boundary

Introduce explicit diagnosis/recovery/replan flow.

### R6 — Deterministic compatibility planner

Use the existing deterministic reasoner as the initial planner behind the new boundary.

### R7 — Real-device migration tests

Prove P0, P1, and P2 behavior through the rebuilt runtime.

### R8 — LLM reasoner

Only after R1-R7 are stable, add an LLM behind the same planner interface.

### R9 — Memory and skill learning

Add reusable task knowledge without turning memory into hard-coded macros.

## Current conclusion

The old Nova architecture successfully proved Android control, goal evaluation, multi-step navigation, recovery, and transition handling. Its job as a prototype is complete.

The rebuild should now shift the center of gravity from a deterministic `NavigationLoop` to a task-oriented agent runtime with explicit observation, reasoning, action, verification, recovery, and memory boundaries.

The reference architecture gives us the structural direction. Nova's existing reliability work supplies the parts that are stronger than the reference implementation, especially bounded transition verification and disciplined real-device testing.

**Next coding milestone: R1 — introduce the new task-runtime boundary without breaking the existing Android bridge or tests.**
