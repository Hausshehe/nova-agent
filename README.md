# Nova Agent

Nova is being rebuilt as an **adaptive Android agent**, not a scripted tap macro.

The long-term product goal is a system-level assistant that can be invoked from Android (eventually by holding the Home/assistant button), understand a natural-language goal, operate across apps, verify real-world results, recover from unexpected states, and optionally keep working on a long-running goal until a deadline.

## Product vision

### Instant assistant

From anywhere on Android:

```text
Hold Home / invoke Nova
        ↓
Nova understands the request
        ↓
observe Android reality
        ↓
reason about the current state
        ↓
act
        ↓
verify
        ↓
replan until the goal is actually complete
```

The invocation mechanism is only the front door. The same Nova runtime should also support direct app/bridge requests and long-running tasks.

### Long-running agent

Nova should eventually accept requests such as:

> "Nova, finish this by 8 AM."

The goal is persisted as a task with a deadline, progress/evidence, current state, and next objective. Nova can sleep/wait between steps, resume after process restarts, recover from failures, and notify the user when the goal is genuinely complete.

The deadline is a task constraint, not merely a reminder.

## Core architecture

```text
User Goal
   ↓
Nova Task / Agent Runtime
   ↓
Observe current Android reality
   ├── Accessibility / structured UI state
   └── Screenshot → Gemini Vision when visual understanding is needed
   ↓
DeepSeek Native Reasoning
   ↓
Structured next action / decision
   ↓
Nova resolves that decision against the CURRENT UI
   ↓
Android action
   ↓
Fresh observation
   ↓
Goal evaluation + verification
   ├── complete → done
   └── mismatch/failure → replan with fresh reality
```

### Design principles

- **Adaptive, not coordinate/script driven.**
- Android UI changes are expected. Nova should re-observe and reason from the new state rather than depend on fixed coordinates or fragile sequences.
- **Goal completion matters more than action acceptance.**
- Accessibility is the primary structured observation/action channel.
- Gemini is the visual specialist, not the overall agent brain.
- DeepSeek is the general reasoning engine.
- Nova owns orchestration, task state, Android capabilities, verification, recovery, persistence, and scheduling.
- Keep provider boundaries clean so another provider can be added later without redesigning the runtime, but do not build a provider zoo without a real need.
- Every important state transition should be verified on the real Android device.
- Avoid arbitrary sleeps; wait for observable readiness/state transitions.

## Current verified DeepSeek integration

The repository now contains a working **native DeepSeek Android bridge**.

It does **not** use:

- a DeepSeek API key;
- a standalone HTTP client to DeepSeek's backend;
- credential/token/cookie extraction;
- replay of authenticated requests;
- auth or PoW bypass;
- a manually typed DeepSeek UI message.

Instead, Nova uses a hook loaded inside the DeepSeek process and invokes DeepSeek's own in-process session/completion machinery.

### Native path

```text
Nova BridgeServer :18765
        ↓
DeepSeek native bridge :18766
        ↓
DeepSeek x05.K0(...)
        ↓
kk1
        ↓
np1 session
        ↓
np1.U(...)
        ↓
DeepSeek's native request/completion pipeline
        ↓
native SSE stream
        ↓
x21 / response hooks
        ↓
Nova response collector
        ↓
BridgeServer
```

### Cold start

If DeepSeek is completely stopped, Nova's `deepseek_native_prompt` command automatically bootstraps `com.deepseek.chat.MainActivity`.

The bootstrap hooks:

1. capture the DeepSeek Activity;
2. hide its window as early as Android allows;
3. wait for `x05.K0` to resolve `kk1`;
4. resolve the live `np1` session;
5. move the DeepSeek task back so the user's previous app regains focus.

There is currently a small Android-controlled visual flash during a cold start. It is accepted for now. Once the session is alive, subsequent native prompts reuse the live session and do not intentionally relaunch the DeepSeek Activity.

The user's foreground app is not navigated/restarted by this mechanism. The intended result after the brief bootstrap is that the previous app/task is foreground again.

### Verified cold-start result

After force-stopping DeepSeek, the following real-device request succeeded:

```bash
printf '%s\n' '{"command":"deepseek_native_prompt","prompt":"Reply with exactly COLD_NATIVE_OK"}' | nc 127.0.0.1 18765
```

Result:

```json
{"ok":true,"accepted":true,"completed":true,"text":"COLD_NATIVE_OK"}
```

The race condition where port 18766 was listening before `liveNp1` existed was fixed by waiting for actual native-session readiness rather than treating an open socket as sufficient.

## Important implementation files

- `app/src/main/java/com/hausshehe/nova/BridgeServer.kt`
  - Nova localhost bridge on `127.0.0.1:18765`
  - automatic DeepSeek cold bootstrap
  - native prompt request/response coordination
- `app/src/main/java/com/hausshehe/nova/DeepSeekNativeInvokeProbe.java`
  - injected into `com.deepseek.chat`
  - captures the live `kk1 → np1` session
  - exposes localhost `127.0.0.1:18766`
  - invokes DeepSeek's native `np1.U(...)`
  - waits for actual session readiness
- existing Nova Accessibility/observation code
  - remains the Android capability boundary

## DeepSeek investigation facts worth preserving

- DeepSeek `x05.K0` is the proven session-resolution point.
- `K0` returns `kk1`.
- `kk1.d.getValue().c` yields the live `np1`.
- `np1.Q() → be1.l() → lr1.a → it8.k()` resolves the native `n1` used by `np1.U`.
- The working invocation uses the observed default mask `0x4c`.
- Native response events are observed through the existing `x21`/response-hook path.
- The DeepSeek app is currently installed as version 2.5.2 on the phone, while much of the reverse-engineering was performed against the supplied 2.5.1 APK. Do not silently assume those versions are identical; re-check if internals change.

## Next engineering phase

The cold-start bridge is now a **backend capability**, not the product itself.

Next:

1. Find/confirm Nova's reasoning/task-runtime boundary.
2. Put DeepSeek Native behind that reasoning boundary.
3. Make a real Nova goal invoke DeepSeek without a diagnostic command.
4. Feed fresh accessibility state to the reasoner.
5. Add Gemini Vision as the visual observation specialist.
6. Implement structured action selection and current-state target resolution.
7. Verify every action against fresh Android state.
8. Add recovery/replanning.
9. Add persistent long-running task state and deadline handling.
10. Add background/resume execution for overnight tasks.
11. Build the Nova assistant UI/invocation surface.
12. Investigate Android's system-assistant/Home-button role so holding Home invokes Nova instead of the current assistant.
13. Keep the system adaptive: no hard-coded UI coordinates or predetermined tap sequences.

## Handoff

The detailed handoff for continuing this project in another coding agent is:

`docs/NOVA_CLAUDE_HANDOFF.md`

It documents the verified DeepSeek connection, bootstrap sequence, commits, boundaries, current state, and the planned product architecture.
