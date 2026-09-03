# Nova runtime rebuild

This branch is intentionally based on `e6b63c23c7e65ad68bf3e2012f7bead137abe438`, before the accumulated task-runtime/recovery layers.

## Architecture

`WorldState -> ReasoningContext -> ReasoningProvider -> runtime guard -> AndroidBridge -> fresh WorldState -> effect evaluation -> repeat`

There is one authoritative task loop: `agent.task_runtime_clean.CleanTaskRuntime`.

Groq is a reasoning provider, not a task executor. It proposes one structured action from the current observation. Runtime validation remains deterministic.

## Safety invariants

1. Action-goal labels already visible in the UI do not count as completion before an action occurs.
2. Every executed action is followed by a fresh observation before the next decision.
3. An action producing prerequisite/failure evidence is marked blocked.
4. A blocked action cannot be executed again while the same observable UI state remains unchanged.
5. Observation identity is not used as a proxy for UI change.
6. A bridge/observation timeout does not reuse the pre-action state as if it were fresh.

## Intentionally not ported yet

The later `TaskExecutor`, `TaskState`, `ActionGuard`, `RecoveryEngine`, and duplicate `NavigationLoop` layers are not copied into this branch. They were the source of the architecture drift being investigated.

Scrolling, richer action types, and additional real-device smoke coverage should be ported one capability at a time after the clean loop is validated.
