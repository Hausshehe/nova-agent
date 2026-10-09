# Nova Agent: Project Review and Fixed Plan

**Status date:** 2026-10-09  
**Active branch:** `minimal-gemini-agent`  
**Active direction:** Goal 186  
**Current verified checkpoint:** commit `5e89d22fc4a96491de6b89d87c2392b1ff915541`; 702 tests passed locally on 2026-10-09.  
**Important:** the live autonomous construction benchmark has not yet been rerun after that checkpoint. Unit-test success is not end-to-end proof.

## 1. Mission

Nova should accept an unfamiliar goal, inspect the real environment, discover available resources, construct the required temporary and persistent artifacts, execute a viable plan, observe actual outcomes, recover or replan after failures, and verify the requested result. It must report evidence and genuine blockers honestly rather than narrating actions that never happened.

The example Android calculator is a **benchmark**, not Nova's permanent purpose. Do not specialize Nova around calculators.

## 2. Project history and boundaries

The project has two related generations:

1. **Android navigation runtime:** Android Accessibility, the local bridge, UI observation and target resolution, planning, action execution, verification, and recovery. Earlier verified work also includes real-device navigation/replanning checks.
2. **Current Python CLI agent:** `gemini_agent/` provides provider transport, local tools, memory, goal orchestration/state, constructed actions, and outcome checks. Despite historical names such as `GeminiClient`, Cloudflare is the current chosen provider for active work.

The repository currently contains both generations. The root README describes the older Android runtime; `README_GEMINI.md` describes an earlier minimal Gemini-only starting point and is now stale in places. Treat neither document alone as a complete description of the current branch.

The branch `minimal-gemini-agent` is the active working line. GitHub comparison reports it as heavily diverged from `main` (1,812 commits ahead and 53 behind at the time of review), and the repository contains many historical/experimental branches. Do not merge, rebase, delete branches, or try to reconcile the histories as part of Goal 186. First finish and verify the current objective on the active branch.

### Completed directions

Project decisions retained from prior work mark directions **137 and 178–185 as completed**. Keep them closed unless concrete test or runtime evidence shows a specific regression or missing integration required by the current goal. In particular, Goal 178 is not an excuse for an endless stream of speculative autonomy features.

### Active direction: Goal 186

Make Nova capable of transforming an unfamiliar goal into the temporary and persistent artifacts, commands, configurations, and execution steps needed to achieve it with available resources, while validating, recovering, and verifying the constructed solution.

## 3. Current technical picture

- `gemini_agent/client.py` owns provider calls and much of the tool-call / goal-orchestration control flow.
- `gemini_agent/tools.py` contains a broad collection of local, filesystem, Android, system-inspection, capability-repair, world-model, and goal-management tools.
- `goal_state.py` and `goal_state_store.py` track and persist a bounded active goal, success condition, evidence, steps, and recovery history.
- `goal_progress.py` and `goal_completion.py` classify evidence. These are bounded heuristic checks, not proof that an external artifact works by themselves.
- `constructed_action.py` runs structured argv actions without shell interpretation, confines the working directory to Nova's configured filesystem root, and caps each action at 30 seconds. It blocks shell/interpreter executables and shell composition. These are safety constraints, not bugs to bypass casually.
- Tests cover many individual tools and integration contracts. The latest observed full test run passed 702 tests.
- A simple Cloudflare text round-trip was previously verified. A live autonomous construction attempt returned malformed tool-call markup as plain text, so the end-to-end behavior remains unverified.
- The latest code change widened autonomous-goal detection to recognize the benchmark's explicit ownership/continuation language. A regression in goal resumption was then fixed by ensuring resume requests bypass new-goal detection. The resume regression suite and all 702 tests now pass.
- A code-level risk remains in goal-contract extraction: the current heuristic chooses the first sentence as the goal and searches backward for a sentence containing words such as “build” and “result” to use as the success condition. On the calculator benchmark, the reporting sentence may match that heuristic even though it is not the actual success condition. Add a regression test for the exact benchmark prompt before changing this code.

## 4. Fixed execution plan

### Phase A: Lock the baseline

- Stay on `minimal-gemini-agent` and keep Cloudflare as the selected provider.
- Preserve commit `5e89d22` as the current baseline.
- Do not add unrelated capabilities, switch providers, restructure modules, or revisit completed directions.
- Reproduce issues before changing code. Do not infer live behavior from unit tests alone.

### Phase B: Test goal-contract extraction

- Add a regression test using the exact Android calculator benchmark prompt.
- Assert that the extracted goal is the actual requested construction task and the success condition covers an installable APK plus verified arithmetic behavior, not merely a reporting request.
- Keep the existing resume regression test: resuming must preserve the saved goal and original success condition.
- Run the focused tests first, then the complete `test_gemini_*.py` suite.
- Make the smallest code change required by failing evidence. Do not rewrite the goal runtime.

### Phase C: Run one controlled live benchmark

Use Cloudflare only and keep the benchmark prompt fixed for comparability:

> Create a minimal Android calculator app from scratch in a new workspace. Inspect the available environment and discover the necessary tools and build procedure. Create the source files and configuration, build an installable APK, and verify addition, subtraction, multiplication, and division with actual tests. Maintain ownership of this goal through failures: diagnose the evidence, recover or replan, and continue until the success criteria are verified or a genuine environmental blocker is demonstrated. Do not claim success without evidence. Report the workspace, source files, build command, APK path, test results, and any unresolved blockers.

Record observed evidence, not just Nova's final prose:
- the active persisted goal and success condition;
- actual tool calls and returned results;
- workspace and created source/configuration files;
- discovered build tools and exact build command;
- build exit status and APK existence/path;
- actual arithmetic test command and results for all four operations;
- any failed action, diagnosis, recovery, and final state.

### Phase D: Repair only a demonstrated blocker

If the benchmark fails, identify the earliest concrete failed contract: goal entry, goal contract, resource discovery, safe action execution, build environment, test execution, or evidence-based completion. Add a failing regression test, make one coherent minimal change, run focused and full tests, and rerun the live benchmark. Never weaken safety boundaries or invent success just to get a green result.

A genuine environmental blocker is a valid, honest stopping point for that attempt, but it does **not** count as Goal 186 being successfully completed.

### Phase E: Declare completion and stop

Goal 186 is complete only when Nova has completed the unfamiliar construction benchmark with independently observable evidence that the APK exists and the four arithmetic operations pass actual tests, or when a different agreed benchmark proves the same general capability. The final report must include the artifact locations, commands, test evidence, and unresolved issues.

Once the acceptance criteria are met, explicitly declare Goal 186 complete and stop adding capabilities to it. No “one last improvement” treadmill.

## 5. Non-negotiable development protocol

Every change follows this order:

1. **Inspect:** identify the exact failing behavior and current implementation.
2. **Specify:** write a test that fails for that behavior.
3. **Change:** one coherent, minimal patch on GitHub.
4. **Test:** focused tests, then the full suite.
5. **Checkpoint:** commit and pull the known-good code.
6. **Exercise:** test the new behavior on the actual phone/runtime and chosen provider.
7. **Record:** capture evidence and decide whether the acceptance criterion is met.

Do not start another capability until the current one has been tested. Do not call a capability complete because its helper function or unit tests exist. Do not ask the user to supervise every step when the agent's purpose is to own the task. Do not hide uncertainty or environmental blockers.

## 6. Out of scope until Goal 186 is decided

- Provider switching or another provider integration.
- New memory, world-model, portfolio, learning, or Android-navigation features without a demonstrated benchmark blocker.
- Broad refactors of the large `client.py` and `tools.py` modules.
- Merging historical branches or reconciling `main`.
- Reopening directions 137 or 178–185 without evidence of a specific regression.
- Cosmetic documentation cleanup beyond what is necessary to keep this plan accurate.

**Single next task:** test the goal and success-condition extraction against the exact benchmark prompt. Nothing else moves until that contract is correct and the live Cloudflare benchmark has been observed.
