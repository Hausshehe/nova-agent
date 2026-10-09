# Nova composability checkpoint

Date: 2026-10-09
Branch: `minimal-gemini-agent`

## Verified checkpoint: bounded read-only workflow execution and named reuse

Evidence recorded from the TECNO/Termux live run:

- Full regression suite: `723 tests`, `OK` (30.700 seconds).
- Live request explicitly selected `run_workflow`.
- Locally recorded execution evidence reported `status: completed` and `steps_completed: 2`.
- Step 0 executed `calculator` with `6 * 7` and returned `42`.
- Step 1 executed `calculator` with the prior step result reference `{"$step_result": 0}` and returned `42`.
- The CLI displayed the local `run_workflow` result rather than relying solely on the model's prose.
- Named workflow `persistence-check` was saved through Nova with two calculator steps and description `Verify reusable workflow persistence`.
- Nova was exited and restarted; a subsequent request invoked `run_saved_workflow` by name without recreating or resaving the definition.
- The live local execution evidence showed `status: completed`, `steps_completed: 2`, and both step results as `42`.
- Targeted regression suite after evidence-display changes: `13 tests`, `OK`.
- Active agent regression suite: `723 tests`, `OK` (30.071 seconds).
- The broad `unittest discover -s tests -q` run is not clean: three modules require missing `pytest`, and `test_mission_state` imports absent `nova_core.models`. These are separate from the active agent suite and should not be represented as passing.

This verifies bounded read-only composition, persisted named reuse across a real process restart, and independently displayed local execution evidence. It does not establish adaptive selection among workflows, nested composition, universal goal-solving, or safe mutation workflows.

## Existing boundaries to preserve

- Workflows are bounded to eight steps.
- Only explicitly allowlisted, read-only/deterministic handlers are callable from `run_workflow`.
- Prior-step references must point to earlier completed steps.
- Failures stop subsequent steps and produce a failed status.
- Do not widen the allowlist to mutating tools as part of this checkpoint.
- Do not add a second planner, goal manager, memory system, or recovery subsystem.

## Acceptance criteria status

1. **Named workflow reuse:** PASS. Saved definition was invoked after restarting Nova, without resaving.
2. **Validation and safety:** PARTIAL. Tests cover disallowed tools, duplicate/missing names, earlier-step references, failure stops, and the step limit. Do not claim the entire oversized-definition and malformed-store matrix is covered without adding those explicit regressions.
3. **Deterministic execution evidence:** PASS for successful execution; engine tests also verify failed steps stop later execution and return a failed status.
4. **Regression coverage:** PASS for core save/list/reload/reuse, disallowed tools, and failure behavior; coverage of corrupted/oversized persisted stores remains incomplete.
5. **Device/live verification:** PASS. Nova was restarted and its locally recorded `run_saved_workflow` trace matched the saved two-step definition.

## Next decision

The named-workflow persistence increment is complete. Do not add nested workflows, mutating actions, or another planner as a continuation of this increment. If continuing the broader composability direction, the next distinct goal should be **adaptive selection and composition of existing named workflows for a goal**, evaluated against more than one materially different task and with clear evidence that Nova selects reusable definitions rather than generating a bespoke chain each time. Before that, decide whether the known validation gaps need a small hardening pass; do not quietly treat them as already solved.

This checkpoint closes the named persistence/reuse increment. It does not declare adaptive workflow selection or the broader composability direction complete.
