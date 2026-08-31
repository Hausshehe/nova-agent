# Nova Agent

Goal-driven autonomous Android navigation agent.

## Recovery status

This repository is a reconstruction of the last verified working Nova Agent behavior. The original historical checkpoint is no longer available, so `c3833ec` is treated as a historical reference, not as a recoverable commit.

## Verified architecture

- Android Accessibility Service
- Local Android command bridge on `127.0.0.1:18765`
- UI observation and normalized snapshots
- UI target resolution
- Natural-language goal evaluation
- Deterministic planning/reasoning
- Action execution
- Action/result verification
- Multi-step navigation
- Failure recovery and alternate-target selection
- Bounded transition settling

## Intended control loop

`observe -> plan -> act -> observe -> verify -> evaluate -> complete/re-plan`

## Recovery principles

1. Preserve working behavior before adding capabilities.
2. Verify every layer with tests and, where applicable, the real Android device.
3. Avoid arbitrary sleeps; use bounded observation/settling behavior.
4. Keep deterministic behavior stable before introducing an LLM planner.
5. Commit every known-good milestone so failures can be rolled back safely.

## Historical real-device checks

The previous implementation successfully exercised:

- `Tap Test Navigation Action`
- `Complete Navigation Sequence`
- recovery after a failed target

The known sequence used the Nova test UI's navigation controls and verified completion after the final state transition.
