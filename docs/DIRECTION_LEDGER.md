# Nova Direction Ledger

**Status date:** 2026-10-09  
**Active branch:** `minimal-gemini-agent`  
**Authority for current execution:** [NOVA_PROJECT_PLAN.md](NOVA_PROJECT_PLAN.md)  
**Active objective:** Goal 186, evaluated by the existing end-to-end Android calculator benchmark.  
**Purpose of this ledger:** preserve accepted direction status, boundaries, and evidence without turning historical work into a new roadmap.

## Rules for using this ledger

1. Directions 137 and 178–185 are **accepted as complete and frozen**. Do not reopen, extend, rename, split, or replace them merely because a new idea is available or an old evidence record is difficult to retrieve.
2. Reopen a frozen direction only when a concrete regression or missing integration is demonstrated and is necessary for the current explicitly approved objective. Record the specific failing test or runtime observation first.
3. A remembered status and a retrievable evidence artifact are different things. Preserve the accepted status while labeling evidence gaps honestly. Never fill a gap with an invented test result.
4. Goal 186 is the only active direction in the current plan. Do not create another direction or add capabilities while its existing benchmark remains undecided.
5. Keep the current execution protocol: inspect → failing test → minimal change → focused and full tests → checkpoint → actual-runtime test → record evidence. A passing unit suite is not end-to-end proof.
6. The calculator is a **benchmark**, not a reason to specialize Nova permanently around calculators.

## Accepted direction history

### Direction 137: Bounded self-extension, self-repair, and self-improvement

**Status:** COMPLETE · FROZEN

**Accepted scope:** a bounded cycle for discovering and validating extensions, executing and verifying them, recovering or replanning after failure, and persisting verified experience. Repair follows diagnosis, a bounded repair transaction, independent verification, and recorded acceptance. Improvement is based on verified successes, failures, and recovery strategies, not unrestricted self-modification.

**Recorded evidence:** prior project history reports real-TECNO verification of the bounded architecture.

**Boundary:** this is not universal or unconstrained self-evolution. Do not modify these systems absent an explicit new goal and concrete evidence of a relevant defect.

### Direction 178: Goal-Driven Autonomy

**Status:** COMPLETE · FROZEN

**Acceptance intent:** take an unfamiliar multi-step goal; understand and plan it; select tools; execute and observe; accumulate evidence; verify the whole goal; recover or replan when needed; use extension, repair, and verified experience when necessary; stop safely; and report truthfully.

**Recorded evidence:** prior history records a real-device goal involving battery state and current date, with both goal completion and runtime status reported as `VERIFIED`. The historical suite count was 502/502.

**Boundary:** the acceptance of Direction 178 is not permission to add an endless stream of autonomy features. No further 178 capabilities.

### Direction 179: Reliable Long-Horizon Autonomy

**Status:** COMPLETE · FROZEN

**Acceptance intent:** maintain a bounded goal-step ledger (maximum 16 steps), record action/status/evidence, distinguish `EXECUTED`, `VERIFIED`, and `FAILED`, avoid repeating successful steps, preserve failures for recovery and replanning, and verify ordered completion.

**Recorded evidence:** prior history reports a real-device test in which a missing command was attempted once and recorded as failed without a duplicate retry; Nova replanned to the current-date capability, checked the ordered goal, and reported `COMPLETED`. The historical suite count was 515/515.

**Boundary:** no further 179 capabilities.

### Direction 180: Adaptive Autonomous Competence

**Status:** COMPLETE · FROZEN

**Acceptance intent:** adapt through alternative mechanisms and multiple observations; distinguish evidence from uncertainty; stop when further attempts produce no new evidence; and report uncertainty honestly.

**Recorded sub-capability:** 180.1, Capability Readiness Self-Model, assesses declared capabilities, handlers, and persisted verification as `VERIFIED`, `UNVERIFIED`, `AVAILABLE_BUT_UNVERIFIED`, or `UNAVAILABLE`. It is read-only and includes relevant constraints/history rather than claiming unverified capability.

**Recorded evidence:** prior history reports a real-device readiness assessment showing capabilities available but unverified, with no execution or device change. Historical suite counts include 524/524 for the readiness work.

**Boundary:** accepted as complete within the bounded architecture. Do not reopen it to pursue a broader or universal form of adaptation without an explicit new goal.

### Direction 181: Reality-Grounded Autonomy

**Status:** COMPLETE · FROZEN

**Acceptance intent:** distinguish an action being executed from the requested outcome being achieved; define observable evidence; verify the actual environment; detect expected/observed mismatches; adapt or replan; and stop only when the evidence supports the result.

**Recorded sub-capabilities:** outcome contract, outcome verification, and discrepancy diagnosis. Existing replanning was reused instead of duplicating it.

**Recorded evidence:** prior history reports a real-device mismatch test resulting in `MISMATCH → REPLAN`, with no false success claim and no device-state change. Historical suite count was 545/545.

**Boundary:** no additional 181 framework or sub-direction.

### Direction 182: Generic Autonomous Self-Repair Control Plane

**Status:** COMPLETE · FROZEN (accepted project status)

**Accepted scope:** diagnose → select candidate → perform a bounded repair transaction → execute the repaired capability at most once → persist verification → analyze capability history → accept only when eligible; otherwise remain pending, reverify, or stop safely. Compound workflow routing was corrected so nested execution wording could not hijack the intended control flow.

**Recorded implementation evidence:** prior history records the generic repair control plane and a routing fix at commit `92dd38c1`; historical development suite counts included 439/439 and 443/443.

**Historical evidence gap:** the retrievable records available for this ledger do not establish the final real-device acceptance result. Some earlier records show `REMAIN_PENDING`/`PENDING`. This is an evidence-retrieval gap, not proof of failure, and it does not override the user's accepted frozen status. Do not claim a successful final acceptance test that is not documented, and do not reopen Direction 182 merely to resolve this historical gap.

### Direction 183: Intentional Agency

**Status:** COMPLETE · FROZEN

**Acceptance intent:** turn unfamiliar or ambiguous requests into bounded intent contracts, preserve uncertainty, identify missing evidence, ask the minimum necessary clarifying questions, avoid invented assumptions, and avoid capability execution or device changes while intent remains unresolved.

**Recorded evidence:** prior history reports a real-device test that requested clarification about the target and observable success conditions without assumptions, actions, or device changes. Historical suite count was 560/560.

**Boundary:** do not duplicate its clarification and uncertainty controls in another direction. No additional 183 sub-direction.

### Direction 184: Multi-Goal Agency

**Status:** COMPLETE · FROZEN

**Acceptance intent:** maintain multiple active goals and commitments with independent contracts and statuses; track dependencies and progress; prioritize or defer work; manage interruptions and conflicts; resume or abandon goals; and verify portfolio coherence.

**Recorded evidence:** prior history reports a real-device portfolio with two goals: battery `VERIFIED`, date `ACTIVE/INCONCLUSIVE`, and coherence `VERIFIED`, with no device-state changes. Historical suite count was 599/599.

**Boundary:** the recorded scope explicitly excluded multi-agent collaboration, generic memory, self-learning, and speculative “better planning” additions. No 184.6.

### Direction 185: Internal World Model

**Status:** COMPLETE · FROZEN

**Acceptance intent:** maintain a bounded, structured, evidence-grounded model of entities, states, relationships, history, uncertainty, provenance, and temporal change; revise beliefs and answer queries without inventing unsupported facts.

**Recorded evidence:** prior history reports a real-device query for “battery temperature” returning `UNKNOWN_OR_UNSUPPORTED` with zero matches, no inferred facts/relationships/history, and no device change. Historical suite count was 646/646.

**Boundary:** no additional 185 sub-direction. The documented unsupported query is evidence of honest uncertainty handling, not evidence that the queried temperature was known.

## Current workflow-composition evidence (2026-10-09)

The workflow engine composes bounded, allowlisted steps sequentially, passes earlier results to later steps, validates references before execution, and stops on failure. Workflow execution is distinct from autonomous selection of the workflow.

**Recorded live checks:**

- Two calculator steps: step 0 computes `6 * 7 = 42`; step 1 consumes step 0's result and returns `42`. Workflow completed.
- Failure stop: `6 * 7`, then `1 / 0`, then `10 + 5`. The workflow failed at division by zero and did not execute step 2.
- Cross-capability composition: `get_file_name("nova-test.txt")` returned `nova-test.txt`; `get_file_extension` consumed that result and returned `.txt`.

**Regression suite:** the latest user-reported run completed 737 tests successfully.

**Known limit:** structured JSON-path references are unit-tested but have not yet been verified end to end with a real JSON-producing workflow step. Do not add a new tool solely to tick this box. The live prompts above explicitly specified their steps, so these checks prove executor composition and failure behavior, not that Nova independently discovers and selects a useful capability combination for an unfamiliar goal.

## Only active objective: Goal 186

Follow [NOVA_PROJECT_PLAN.md](NOVA_PROJECT_PLAN.md) for the fixed execution plan and exact benchmark prompt.

**Success requires observable end-to-end evidence** that Nova, without manual code edits or step-by-step babysitting, can construct a minimal Android calculator app in a new workspace, build an installable APK, and independently test addition, subtraction, multiplication, and division. Record the actual workspace, source/configuration files, build command and exit status, APK path/existence, test command/results, failures, diagnosis, recovery, and final state.

A model's claim, a generated source file, a passing unit suite, or an APK that was never installed/tested is not sufficient proof of the whole goal. A genuine environmental blocker may justify stopping an attempt honestly, but does not mean Goal 186 has passed.

**Stop rule:** when the acceptance criteria in the project plan are demonstrably met, explicitly declare Goal 186 complete and stop adding capabilities to it. Do not invent Goal 187 or another sub-direction. Any later work needs a genuinely new explicit objective.

## Evidence hygiene

- Counts and device results above are historical records retrieved from project conversation history, not a claim that those old suites were rerun on 2026-10-09.
- The current branch plan's recorded 702-test checkpoint and the later 737-test run refer to different points in development; keep dates and checkpoint identity attached when updating evidence.
- If an exact old artifact cannot be retrieved, label that limitation. Never turn “not found” into “never happened,” or into “passed.”
- Update this ledger only when new evidence changes a status, resolves a recorded gap, or clarifies an accepted boundary. Do not turn it into a changelog of every small code edit.
