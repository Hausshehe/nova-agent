# Nova Rebuild Architecture and Product Direction

This document supersedes the earlier "LLM comes only after R1-R7" ordering. The DeepSeek native bridge is now proven on a real device, so the next step is to integrate it into the task runtime while preserving the adaptive architecture.

## Product target

Nova is intended to become:

1. an Android system assistant invoked from anywhere (eventually Home/assistant-button invocation); and
2. a persistent long-running agent that can accept deadline-based goals such as "finish this by 8 AM".

The product is **goal-driven and reality-driven**, not a macro recorder.

## Target loop

```text
Goal
 ↓
Persistent Task State
 ↓
Fresh Observation
 ├── Accessibility
 └── Gemini Vision when needed
 ↓
DeepSeek reasoning
 ↓
Structured decision
 ↓
Current-state action resolution
 ↓
Android action
 ↓
Fresh observation
 ↓
Goal verification
 ├── complete → DONE
 └── mismatch/failure → diagnose + replan
```

## Responsibility boundaries

### Nova runtime

Owns the task and reality:

- task lifecycle
- persistence
- deadlines
- observation
- action execution
- current-state target resolution
- verification
- recovery
- replanning
- background/resume
- user-facing assistant entry point

### DeepSeek

Owns general reasoning:

- understand the goal
- interpret current state
- propose the next decision/action
- reason about unexpected states
- replan

### Gemini Vision

Owns visual perception:

- interpret screenshots
- identify visual targets
- supplement incomplete accessibility data

## Adaptive requirement

Android and app UIs will change. Nova must adapt by observing current state before each meaningful decision/action.

Never encode the product around fixed coordinates or predetermined tap sequences.

The model's output is a **decision**, not permission to blindly manipulate Android.

## Long-running task model

A long-running task must persist:

- goal
- deadline
- status
- current subgoal
- verified state/evidence
- last action/result
- recovery state
- next objective
- timestamps

Process death must not erase the task.

On resume, Nova re-observes the device and re-evaluates the persisted state instead of blindly continuing from an old screen assumption.

## Assistant invocation

The eventual flow is:

```text
Hold Home / invoke assistant
 ↓
Nova assistant surface
 ↓
same task runtime
```

The invocation surface must remain independent of the agent core so Nova can also be triggered through other entry points.

## Verified DeepSeek backend

The native bridge is already proven.

Nova localhost bridge:

`127.0.0.1:18765`

DeepSeek in-process control bridge:

`127.0.0.1:18766`

The path is:

```text
Nova BridgeServer
 ↓
DeepSeekNativeInvokeProbe
 ↓
x05.K0(...)
 ↓
kk1
 ↓
kk1.d.getValue().c
 ↓
np1
 ↓
np1.Q() → be1.l() → lr1.a → it8.k()
 ↓
np1.U(..., mask 0x4c)
 ↓
DeepSeek native completion machinery
 ↓
x21 / n63 response hooks
 ↓
Nova response collector
```

Cold start is automatic if the native bridge is absent. The bridge waits for actual `np1` readiness, not just port availability.

## Verified cold-start contract

Real-device result:

```json
{"ok":true,"accepted":true,"completed":true,"text":"COLD_NATIVE_OK"}
```

A small visual DeepSeek flash remains during cold bootstrap and is accepted as a current cosmetic limitation.

## Migration direction

The old deterministic navigation implementation remains a regression asset.

The rebuilt runtime should become the long-term orchestration layer:

`Task Executor → Observation → Reasoner → Action → Verification → Recovery/Replan`

The deterministic reasoner can remain as a fallback/testing asset.

## Next milestone

Integrate DeepSeek Native behind the real Nova reasoning boundary.

Then:

1. fresh-state context;
2. structured model decisions;
3. current-state action resolution;
4. verification/replanning;
5. Gemini Vision;
6. persistent long-running tasks;
7. background/resume;
8. assistant UI;
9. Home/assistant integration.

The goal is not "make an LLM control Android". The goal is "make Nova reliably achieve user goals in changing Android reality."
