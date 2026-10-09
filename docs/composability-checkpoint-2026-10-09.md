# Nova composability checkpoint

Date: 2026-10-09
Branch: `minimal-gemini-agent`

## Verified checkpoint: bounded read-only workflow execution

Evidence recorded from the TECNO/Termux live run:

- Full regression suite: `723 tests`, `OK` (30.700 seconds).
- Live request explicitly selected `run_workflow`.
- Locally recorded execution evidence reported `status: completed` and `steps_completed: 2`.
- Step 0 executed `calculator` with `6 * 7` and returned `42`.
- Step 1 executed `calculator` with the prior step result reference `{"$step_result": 0}` and returned `42`.
- The CLI displayed the local `run_workflow` result rather than relying solely on the model's prose.

This verifies one live two-step composition path. It does not establish universal goal-solving, persistent workflow reuse, nested composition, or safe mutation workflows.

## Existing boundaries to preserve

- Workflows are bounded to eight steps.
- Only explicitly allowlisted, read-only/deterministic handlers are callable from `run_workflow`.
- Prior-step references must point to earlier completed steps.
- Failures stop subsequent steps and produce a failed status.
- Do not widen the allowlist to mutating tools as part of this checkpoint.
- Do not add a second planner, goal manager, memory system, or recovery subsystem.

## Remaining composability acceptance criteria

1. **Named workflow reuse:** a workflow can be saved as a bounded definition and invoked later by name, without asking the model to regenerate its steps each time.
2. **Validation and safety:** persisted definitions are schema-validated on save and load; unknown/disallowed tools, malformed references, oversized definitions, and step-limit violations are rejected before execution.
3. **Deterministic execution evidence:** invocation returns the actual step trace, and failed steps cannot be reported as successful.
4. **Regression coverage:** persistence, reload, reuse, invalid definitions, and failure behavior have deterministic tests.
5. **Device/live verification:** after tests pass, one real Nova run proves a saved workflow can be invoked and its local execution evidence matches the stored definition.

## Next candidate, not yet implemented

Investigate the smallest extension to support named, persisted reuse of the existing workflow engine. Reuse the current engine and existing persistence conventions where suitable. Do not implement nested workflows or mutating actions in the same change. Inspect current persistence and path/safety conventions before editing, then make one coherent change and test it before proceeding.

This checkpoint closes the demonstrated one-off read-only composition milestone only. It does not declare the broader composability direction complete.
